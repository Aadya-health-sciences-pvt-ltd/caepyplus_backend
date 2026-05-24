#!/usr/bin/env python3
"""Standalone Alembic migration runner.

Run database migrations without starting the full application server.
Supports overriding the database URL via the ``--db-url`` flag or the
``DATABASE_URL`` environment variable, making it suitable for CI/CD
pipelines, init-containers, and ad-hoc administrative tasks.

Usage examples
--------------
# 1. Use the DATABASE_URL already set in the environment:
    python scripts/migrate.py upgrade head

# 2. Override the database URL on the command line:
    python scripts/migrate.py --db-url postgresql+asyncpg://user:pass@host/db upgrade head

# 3. Downgrade one revision:
    python scripts/migrate.py downgrade -1

# 4. Print current migration state:
    python scripts/migrate.py current

# 5. Show migration history:
    python scripts/migrate.py history

# 6. Show pending migrations:
    python scripts/migrate.py heads

# 7. Existing DB but alembic_version missing (avoids re-running 001 CREATE TABLE):
    python scripts/migrate.py detect
    python scripts/migrate.py stamp 001          # revision that matches current schema
    python scripts/migrate.py upgrade head       # applies only 002..head

# 8. Detect + stamp (+ optional upgrade) in one step:
    python scripts/migrate.py baseline --upgrade

Environment variables
---------------------
DATABASE_URL     Override the database connection string (takes lower priority
                 than --db-url).
SEED_ADMIN_PHONE Phone number for the initial admin user seed (default: +910000000000).
SEED_ADMIN_EMAIL Email for the initial admin user seed (default: admin@linqmd.com).

Notes
-----
- This script must be run from the repository root directory.
- It calls Alembic programmatically so it honours alembic.ini and the
  migrations in alembic/versions/ without spawning a subprocess.
- Schema management is the ONLY responsibility of this script. The
  application server (main.py / uvicorn) never calls create_tables().
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure the repository root is on sys.path so relative imports resolve.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="migrate.py",
        description="Run Alembic migrations with an optional custom database URL.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--db-url",
        metavar="URL",
        default=None,
        help=(
            "Database connection string, e.g. "
            "postgresql+asyncpg://user:pass@host:5432/dbname. "
            "Overrides DATABASE_URL environment variable."
        ),
    )
    parser.add_argument(
        "--alembic-ini",
        metavar="PATH",
        default=str(_REPO_ROOT / "alembic.ini"),
        help="Path to alembic.ini (default: <repo_root>/alembic.ini).",
    )
    # Collect the rest of the args as the alembic command + args
    parser.add_argument(
        "alembic_args",
        nargs=argparse.REMAINDER,
        help=(
            "Alembic sub-command and arguments, e.g. 'upgrade head', "
            "'downgrade -1', 'current', 'history', 'heads'."
        ),
    )
    return parser.parse_args()


def _sync_db_url(db_url: str | None) -> str:
    """Return a synchronous SQLAlchemy URL for introspection queries."""
    from src.app.core.config import get_settings

    url = db_url or os.environ.get("DATABASE_URL")
    if not url:
        url = get_settings().DATABASE_URL
    return url.replace("+asyncpg", "+psycopg2").replace("+aiosqlite", "")


def detect_schema_revision(db_url: str | None = None) -> str | None:
    """Infer the Alembic revision that matches the live database schema.

    Returns ``None`` when the database has no application tables (fresh DB).
    """
    from sqlalchemy import create_engine, inspect, text

    engine = create_engine(_sync_db_url(db_url))
    try:
        with engine.connect() as conn:
            tables = set(inspect(engine).get_table_names())
            if "doctors" not in tables:
                return None

            if "lead_doctors" not in tables:
                return "001"
            if "blogs" not in tables:
                return "002"

            phone_nullable = conn.execute(
                text(
                    """
                    SELECT is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'users'
                      AND column_name = 'phone'
                    """
                )
            ).scalar()
            if phone_nullable == "NO":
                return "003"

            seg_type = conn.execute(
                text(
                    """
                    SELECT data_type, udt_name
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'doctors'
                      AND column_name = 'practice_segments'
                    """
                )
            ).first()
            if seg_type:
                data_type, udt_name = seg_type
                if data_type in ("json", "jsonb") or udt_name in ("json", "jsonb"):
                    return "005"
            return "004"
    finally:
        engine.dispose()


def main() -> int:  # noqa: C901
    """Entry point — returns an exit code."""
    args = _parse_args()

    # ------------------------------------------------------------------
    # Resolve database URL: CLI flag > env var > alembic.ini value
    # ------------------------------------------------------------------
    db_url: str | None = args.db_url or os.environ.get("DATABASE_URL")

    if db_url:
        # Inject the URL into the environment so Alembic's env.py picks it up
        # via the standard DATABASE_URL convention used by this project.
        os.environ["DATABASE_URL"] = db_url
        print(f"[migrate] Using DATABASE_URL: {_redact_url(db_url)}")
    else:
        # Fall back to whatever is in alembic.ini / env.py
        print("[migrate] DATABASE_URL not set; using connection from alembic.ini / env.py")

    # ------------------------------------------------------------------
    # Resolve Alembic command
    # ------------------------------------------------------------------
    alembic_args: list[str] = [a for a in args.alembic_args if a]

    if not alembic_args:
        print(
            "[migrate] No Alembic command supplied. "
            "Try: python scripts/migrate.py upgrade head",
            file=sys.stderr,
        )
        return 1

    # ------------------------------------------------------------------
    # Run Alembic programmatically
    # ------------------------------------------------------------------
    try:
        from alembic import command as alembic_command
        from alembic.config import Config as AlembicConfig
    except ImportError:
        print(
            "[migrate] ERROR: alembic is not installed. "
            "Run: pip install alembic",
            file=sys.stderr,
        )
        return 1

    alembic_cfg = AlembicConfig(args.alembic_ini)

    # Override sqlalchemy.url in the Alembic config when a URL is provided.
    # Alembic's env.py for this project reads DATABASE_URL from the environment,
    # so setting the env var above is usually sufficient. The explicit override
    # below is a belt-and-suspenders guard.
    if db_url:
        # Convert asyncpg URLs to sync psycopg2 for Alembic's offline mode,
        # but keep asyncpg for online (async) mode — env.py handles this.
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    sub_command = alembic_args[0]
    extra = alembic_args[1:]

    print(f"[migrate] Running: alembic {' '.join(alembic_args)}")

    try:
        if sub_command == "upgrade":
            revision = extra[0] if extra else "head"
            alembic_command.upgrade(alembic_cfg, revision)

        elif sub_command == "downgrade":
            revision = extra[0] if extra else "-1"
            alembic_command.downgrade(alembic_cfg, revision)

        elif sub_command == "current":
            alembic_command.current(alembic_cfg, verbose=True)

        elif sub_command == "history":
            alembic_command.history(alembic_cfg, verbose=("--verbose" in extra or "-v" in extra))

        elif sub_command == "heads":
            alembic_command.heads(alembic_cfg, verbose=True)

        elif sub_command == "revision":
            # Allow generating a new migration via this script
            message = None
            autogenerate = "--autogenerate" in extra
            for i, arg in enumerate(extra):
                if arg in ("-m", "--message") and i + 1 < len(extra):
                    message = extra[i + 1]
            alembic_command.revision(
                alembic_cfg,
                message=message,
                autogenerate=autogenerate,
            )

        elif sub_command == "stamp":
            revision = extra[0] if extra else "head"
            alembic_command.stamp(alembic_cfg, revision)

        elif sub_command == "detect":
            revision = detect_schema_revision(db_url)
            if revision is None:
                print("[migrate] No application tables found — use 'upgrade head' on a fresh database.")
            else:
                print(f"[migrate] Suggested stamp revision: {revision}")
                print(
                    f"[migrate] Next: python scripts/migrate.py stamp {revision}"
                    + (" && python scripts/migrate.py upgrade head" if revision != "005" else "")
                )

        elif sub_command == "baseline":
            explicit = next((a for a in extra if not a.startswith("-")), None)
            do_upgrade = "--upgrade" in extra
            revision = explicit or detect_schema_revision(db_url)
            if revision is None:
                print(
                    "[migrate] ERROR: cannot baseline — no application tables. "
                    "Use 'upgrade head' for a fresh database.",
                    file=sys.stderr,
                )
                return 1
            print(f"[migrate] Stamping database at revision {revision} (no DDL executed).")
            alembic_command.stamp(alembic_cfg, revision)
            if do_upgrade:
                print("[migrate] Applying pending migrations: upgrade head")
                alembic_command.upgrade(alembic_cfg, "head")

        else:
            print(
                f"[migrate] ERROR: unknown sub-command '{sub_command}'. "
                "Supported: upgrade, downgrade, current, history, heads, revision, "
                "stamp, detect, baseline.",
                file=sys.stderr,
            )
            return 1

    except Exception as exc:  # noqa: BLE001
        print(f"[migrate] ERROR: {exc}", file=sys.stderr)
        return 1

    print("[migrate] Done.")
    return 0


def _redact_url(url: str) -> str:
    """Return the URL with the password replaced by '***' for safe logging."""
    try:
        # Minimal redaction without pulling in extra deps
        if "@" in url and "://" in url:
            scheme_creds, rest = url.split("@", 1)
            if ":" in scheme_creds.split("://", 1)[-1]:
                scheme, creds = scheme_creds.split("://", 1)
                user, _ = creds.rsplit(":", 1)
                return f"{scheme}://{user}:***@{rest}"
    except Exception:  # noqa: BLE001
        pass
    return url


if __name__ == "__main__":
    sys.exit(main())
