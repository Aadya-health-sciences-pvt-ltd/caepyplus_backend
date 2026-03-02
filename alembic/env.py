"""Alembic Environment Configuration.

Supports two modes:
    1. Application mode (default): Reads DATABASE_URL from app settings
    2. Standalone mode: Pass DB connection via environment variable or CLI

Standalone usage (run migrations without the full app):
    # Via environment variable:
    ALEMBIC_DATABASE_URL=postgresql://user:pass@host:5432/dbname alembic upgrade head

    # Via alembic -x flag:
    alembic -x db_url=postgresql://user:pass@host:5432/dbname upgrade head

    # Generate SQL only (offline mode):
    ALEMBIC_DATABASE_URL=postgresql://... alembic upgrade head --sql
"""

from logging.config import fileConfig
import os
import sys

from alembic import context
from sqlalchemy import pool, engine_from_config

# Ensure project root is on sys.path so `src` is importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Alembic Config object
config = context.config

# ---------------------------------------------------------------------------
# Resolve database URL: CLI flag > env var > app settings
# ---------------------------------------------------------------------------
def _resolve_database_url() -> str:
    """Determine the database URL from available sources.

    Priority:
        1. ``-x db_url=...`` passed on the alembic CLI
        2. ``ALEMBIC_DATABASE_URL`` environment variable
        3. Application settings (requires full app importable)

    Returns:
        Synchronous (psycopg2) database URL string.

    Raises:
        RuntimeError: If no database URL can be resolved.
    """
    # 1. Check CLI -x flag
    cli_url = context.get_x_argument(as_dictionary=True).get("db_url")
    if cli_url:
        return _to_sync_url(cli_url)

    # 2. Check environment variables — both ALEMBIC_DATABASE_URL (alembic-specific)
    #    and the standard DATABASE_URL (set by scripts/migrate.py and most PaaS
    #    platforms) are accepted.
    env_url = os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if env_url:
        return _to_sync_url(env_url)

    # 3. Fall back to application settings
    try:
        from src.app.core.config import get_settings

        settings = get_settings()
        return _to_sync_url(settings.DATABASE_URL)
    except Exception as exc:
        raise RuntimeError(
            "Cannot resolve database URL. Provide one of:\n"
            "  1. alembic -x db_url=postgresql://... upgrade head\n"
            "  2. ALEMBIC_DATABASE_URL=postgresql://... alembic upgrade head\n"
            "  3. Ensure app settings are importable (DATABASE_URL in .env)\n"
            f"Original error: {exc}"
        ) from exc


def _to_sync_url(url: str) -> str:
    """Convert an async database URL to a synchronous one for Alembic."""
    return url.replace("+asyncpg", "+psycopg2").replace("+aiosqlite", "")


# Resolve and set the URL
sync_url = _resolve_database_url()
config.set_main_option("sqlalchemy.url", sync_url)

# ---------------------------------------------------------------------------
# Import models to register them with SQLAlchemy metadata
# ---------------------------------------------------------------------------
from src.app.db.session import Base  # noqa: E402

# Import all model modules so their tables appear in Base.metadata
from src.app.models import (  # noqa: E402, F401
    Doctor,
    DoctorIdentity,
    DoctorMedia,
    DoctorStatusHistory,
    DropdownOption,
    User,
)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL script instead of executing against database.
    Useful for generating migration SQL for DBA review.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (synchronous).

    Creates engine and runs migrations against the database.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
