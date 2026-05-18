#!/usr/bin/env python3
"""Re-seed dropdown option values into the database.

The canonical seed data lives in the Alembic migration
``alembic/versions/001_initial_schema.py`` (``_DROPDOWN_SEED`` dict).
This script re-runs that seed using the same idempotent
``ON CONFLICT (field_name, value) DO NOTHING`` logic, so it is safe to
run against a database that already has values.

Usage
-----
# Seed using the DATABASE_URL env var:
    python scripts/seed_dropdown_values.py

# Override the database URL on the command line:
    python scripts/seed_dropdown_values.py --db-url postgresql+asyncpg://...

# Dry-run (show counts without writing):
    python scripts/seed_dropdown_values.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Import seed data from the single source of truth — the migration file.
# The migration module name starts with a digit so we use importlib.
import importlib.util as _ilu

_migration_path = _REPO_ROOT / "alembic" / "versions" / "001_initial_schema.py"
_spec = _ilu.spec_from_file_location("_migration_001", _migration_path)
assert _spec and _spec.loader, f"Cannot load migration from {_migration_path}"
_migration_module = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_migration_module)  # type: ignore[union-attr]
_DROPDOWN_SEED: dict[str, list[str]] = _migration_module._DROPDOWN_SEED

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def _run_seed(db_url: str) -> None:
    """Execute the idempotent dropdown seed against the live database."""
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(db_url, echo=False)
    total_attempted = sum(len(v) for v in _DROPDOWN_SEED.values())
    logger.info(
        "Seeding %d values across %d fields (ON CONFLICT DO NOTHING)",
        total_attempted,
        len(_DROPDOWN_SEED),
    )

    async with engine.begin() as conn:
        for field_name, values in _DROPDOWN_SEED.items():
            for value in values:
                await conn.execute(
                    sa.text(
                        """
                        INSERT INTO dropdown_options (field_name, value, created_at, updated_at)
                        VALUES (:field_name, :value, now(), now())
                        ON CONFLICT (field_name, value) DO NOTHING
                        """
                    ),
                    {"field_name": field_name, "value": value},
                )
            logger.info("  %-40s  %d values", field_name, len(values))

    await engine.dispose()
    logger.info("Seed complete.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-url", metavar="URL", default=None, help="Database connection string (overrides DATABASE_URL env var)")
    parser.add_argument("--dry-run", action="store_true", help="Print counts without writing to the database")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.dry_run:
        print("\n=== DRY RUN — values that would be seeded ===\n")
        total = 0
        for field_name, values in _DROPDOWN_SEED.items():
            print(f"{field_name} ({len(values)} values):")
            for value in values[:5]:
                print(f"  - {value}")
            if len(values) > 5:
                print(f"  ... and {len(values) - 5} more")
            total += len(values)
        print(f"\nTotal: {total} values across {len(_DROPDOWN_SEED)} fields\n")
        return

    db_url = args.db_url or os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL is not set. Use --db-url or export DATABASE_URL.", file=sys.stderr)
        sys.exit(1)

    asyncio.run(_run_seed(db_url))


if __name__ == "__main__":
    main()
