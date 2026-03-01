#!/usr/bin/env bash
# ============================================
# entrypoint.sh — Doctor Onboarding Service
# ============================================
# This script runs inside the Docker container at startup.
# It performs two tasks in sequence:
#   1. Run Alembic migrations (idempotent — safe to run on every startup)
#   2. Start the uvicorn API server
#
# USAGE (set in Dockerfile):
#   ENTRYPOINT ["/app/entrypoint.sh"]
# ============================================

set -euo pipefail   # Exit on error, unset vars, or pipe failures

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'  # No Colour

log()  { echo -e "${GREEN}[entrypoint]${NC} $*"; }
warn() { echo -e "${YELLOW}[entrypoint]${NC} $*"; }
err()  { echo -e "${RED}[entrypoint] ERROR:${NC} $*" >&2; }

# ── 1. Validate DATABASE_URL is set ──────────────────────────────────────────
if [[ -z "${DATABASE_URL:-}" ]]; then
    err "DATABASE_URL environment variable is not set."
    err "Pass it via docker-compose environment: or --env-file."
    exit 1
fi

# ── 2. Wait for PostgreSQL to be ready ───────────────────────────────────────
# docker-compose healthcheck handles this for local dev, but we add a
# belt-and-suspenders check here for cloud/k8s deployments where the DB
# container might not yet accept connections when this container starts.

log "Waiting for PostgreSQL to accept connections..."

MAX_RETRIES=30
RETRY_INTERVAL=2
RETRIES=0

# Extract host and port from DATABASE_URL for the connectivity check.
# Expected format: postgresql+asyncpg://user:pass@host:port/dbname
DB_HOST=$(echo "$DATABASE_URL" | sed -E 's|.*@([^:/]+).*|\1|')
DB_PORT=$(echo "$DATABASE_URL" | sed -E 's|.*:([0-9]+)/.*|\1|')
DB_PORT="${DB_PORT:-5432}"

until python -c "
import socket, sys
try:
    s = socket.create_connection(('${DB_HOST}', ${DB_PORT}), timeout=2)
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
    RETRIES=$((RETRIES + 1))
    if [[ $RETRIES -ge $MAX_RETRIES ]]; then
        err "PostgreSQL at ${DB_HOST}:${DB_PORT} did not become ready after $((MAX_RETRIES * RETRY_INTERVAL))s."
        exit 1
    fi
    warn "PostgreSQL not ready yet (attempt ${RETRIES}/${MAX_RETRIES}). Retrying in ${RETRY_INTERVAL}s..."
    sleep "$RETRY_INTERVAL"
done

log "PostgreSQL is ready at ${DB_HOST}:${DB_PORT}."

# ── 3. Run Alembic migrations ─────────────────────────────────────────────────
# `alembic upgrade head` is idempotent — it applies only pending migrations.
# If the database is already up to date, this is a no-op.
log "Running database migrations (alembic upgrade head)..."

if ! alembic upgrade head; then
    err "Alembic migrations FAILED. Aborting startup."
    err "Fix the migration error and redeploy. The database has NOT been changed."
    exit 1
fi

log "Database migrations applied successfully."

# ── 4. (Optional) Seed dropdown values ───────────────────────────────────────
# Uncomment the lines below to seed initial dropdown data on first run.
# The seed script is idempotent (uses INSERT ... ON CONFLICT DO NOTHING).
#
# if [[ "${SEED_DROPDOWNS:-false}" == "true" ]]; then
#     log "Seeding dropdown values..."
#     python scripts/seed_dropdown_values.py || warn "Seed script failed (non-fatal)."
# fi

# ── 5. Start the application ──────────────────────────────────────────────────
WORKERS="${UVICORN_WORKERS:-1}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
LOG_LEVEL_LOWER=$(echo "${LOG_LEVEL:-info}" | tr '[:upper:]' '[:lower:]')

log "Starting uvicorn: host=${HOST} port=${PORT} workers=${WORKERS} log-level=${LOG_LEVEL_LOWER}"
log "──────────────────────────────────────────────────────────────────────"

# NOTE ON WORKER COUNT:
# The voice-onboarding feature uses InMemorySessionStore by default, which is
# process-local.  With multiple workers, sessions created by one worker are
# invisible to others — requests may get 404 on different workers.
#
# Keep UVICORN_WORKERS=1 (the default) until a Redis-backed session store is
# configured.  See Dockerfile comment for more detail.

exec uvicorn src.app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level "$LOG_LEVEL_LOWER"
