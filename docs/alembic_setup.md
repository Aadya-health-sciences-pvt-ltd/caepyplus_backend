# Alembic Setup & Migration Guide

**Project:** Doctor Onboarding Smart-Fill API  
**Migration Tool:** Alembic 1.x with SQLAlchemy 2.0  
**Last Updated:** 2026-02-28  

---

## Overview

This project uses **Alembic** for database schema management. The entire schema is expressed in a single consolidated migration (`001_initial_schema.py`). Alembic is configured to work in three modes:

1. **Application mode** — reads `DATABASE_URL` from app settings (`.env`)
2. **Environment variable mode** — uses `ALEMBIC_DATABASE_URL` or `DATABASE_URL` directly
3. **CLI flag mode** — pass `db_url` inline on the command

---

## Project Structure

```
├── alembic.ini              # Alembic configuration (logging, file templates)
├── alembic/
│   ├── env.py               # Environment config (DB URL resolution, model imports)
│   ├── script.py.mako       # Migration file template
│   └── versions/
│       └── 001_initial_schema.py   # Single consolidated migration (7 tables + seed data)
```

---

## Database URL Resolution

`alembic/env.py` resolves the database URL with this **priority order**:

| Priority | Source | How to Use |
|----------|--------|------------|
| **1 (highest)** | CLI `-x` flag | `alembic -x db_url=postgresql://... upgrade head` |
| **2** | `ALEMBIC_DATABASE_URL` env var | `export ALEMBIC_DATABASE_URL=postgresql://...` |
| **2** | `DATABASE_URL` env var | `export DATABASE_URL=postgresql+asyncpg://...` |
| **3 (fallback)** | App settings | Reads from `.env` via `src.app.core.config.get_settings()` |

> **Async → Sync conversion:** Alembic automatically converts async driver URLs to sync ones:
> - `postgresql+asyncpg://` → `postgresql+psycopg2://`
> - `sqlite+aiosqlite://` → `sqlite://`
>
> You can pass the same `DATABASE_URL` used by the app — no manual conversion needed.

---

## Common Commands

### Apply Migrations

```bash
# Using app settings (.env file)
alembic upgrade head

# Using a custom database URL
ALEMBIC_DATABASE_URL=postgresql://user:pass@host:5432/mydb alembic upgrade head

# Using CLI flag
alembic -x db_url=postgresql://user:pass@host:5432/mydb upgrade head
```

### Check Current Revision

```bash
alembic current
```

### Roll Back

```bash
# Roll back one step
alembic downgrade -1

# Roll back everything
alembic downgrade base
```

### Generate SQL Without Executing (Offline Mode)

Useful for DBA review or audit — produces a `.sql` file without touching the database:

```bash
ALEMBIC_DATABASE_URL=postgresql://user:pass@host:5432/mydb \
  alembic upgrade head --sql > migration.sql
```

### Create a New Migration

```bash
# Auto-generate from model changes
alembic revision --autogenerate -m "Add new_column to doctors"

# Empty migration (for manual SQL)
alembic revision -m "Custom data migration"
```

> New migration files are automatically formatted with `ruff` (configured in `alembic.ini` under `[post_write_hooks]`).

### View Migration History

```bash
alembic history --verbose
```

---

## Docker / Bootstrap Behaviour

The Docker image runs `uvicorn` directly without an intermediate `entrypoint.sh`. Migrations must be run separately against the database before or during deployment.

### Running Migrations via Docker

To run migrations using the built image:

```bash
# Docker run
docker run -e DATABASE_URL=... doctor-onboarding:latest alembic upgrade head
```

This is the standard approach for:
- A DBA applying migrations separately before deployment
- Running migrations from a CI/CD pipeline before rolling out containers
- Container orchestration platforms like Kubernetes using InitContainers or Jobs

### Local development

For local development, simply run:

```bash
# Run migrations
alembic upgrade head

# Run uvicorn directly
uvicorn src.app.main:app --reload --port 6555
```

---

## Running Against a Custom Database

### Scenario 1: Local Development with a Remote DB

```bash
# Point Alembic at a remote database without changing .env
ALEMBIC_DATABASE_URL=postgresql://admin:secret@db.example.com:5432/doctor_onboarding \
  alembic upgrade head
```

### Scenario 2: Staging / Production Migration

```bash
# Run migrations from your local machine against staging
alembic -x db_url=postgresql://deploy_user:pass@staging-db:5432/doctor_onboarding upgrade head

# Generate SQL for DBA review
alembic -x db_url=postgresql://deploy_user:pass@prod-db:5432/doctor_onboarding \
  upgrade head --sql > prod_migration.sql
```

### Scenario 3: CI/CD Pipeline

```yaml
# GitHub Actions example
- name: Run migrations
  env:
    DATABASE_URL: ${{ secrets.DATABASE_URL }}
  run: alembic upgrade head
```

### Scenario 4: Docker Compose with Custom DB

```yaml
# docker-compose.override.yml
services:
  api:
    environment:
      DATABASE_URL: postgresql+asyncpg://custom_user:custom_pass@external-db:5432/mydb
      SKIP_MIGRATIONS: "false"  # or "true" if DBA handles migrations
```

---

## Existing database (missing `alembic_version`)

If tables already exist but `alembic_version` was dropped or never created, **`upgrade head` will try to re-run migration `001` and fail** with errors like `relation "doctors" already exists`. Alembic does not compare your live schema to migrations automatically; it only tracks applied revisions in `alembic_version`.

**Fix:** stamp the revision that matches what is already in the database, then upgrade:

```bash
# 1. Suggest which revision matches the current schema
python scripts/migrate.py detect

# 2. Record that revision without running DDL (example: schema matches 001 only)
python scripts/migrate.py stamp 001

# 3. Apply only newer migrations (002 → head)
python scripts/migrate.py upgrade head
```

Or in one step (detect + stamp + apply pending migrations):

```bash
python scripts/migrate.py baseline --upgrade
```

| Revision | When to stamp |
|----------|----------------|
| `001` | Has `doctors` / core tables, no `lead_doctors` |
| `002` | Has `lead_doctors`, no `blogs` |
| `003` | Has blog tables, `users.phone` still `NOT NULL` |
| `004` | `users.phone` nullable, `doctors.practice_segments` still `VARCHAR` |
| `005` | `practice_segments` already `JSON` / `JSONB` |
| `006` | Has `doctor_linqmd_credentials` |
| `007` | `verbal_intro_file` already `TEXT` |
| `008` | Has `linq360` schema + dashboard table shells |
| `009` | `workspace_doctor_dashboard` has business columns |
| `010` | `workspace_doctor_dashboard.appointments_json` JSONB array (fully up to date) |

---

## Current Migrations

| Revision | File | Description |
|----------|------|-------------|
| `001` | `001_initial_schema.py` | Complete initial schema: core tables, indexes, seed data |
| `002` | `002_add_lead_doctors.py` | `lead_doctors` table |
| `003` | `003_add_blog_comment_and_keyword_models.py` | `blogs`, `blog_comments`, `blog_keywords` |
| `004` | `004_users_phone_nullable.py` | `users.phone` nullable |
| `005` | `005_practice_segments_json.py` | `doctors.practice_segments` → JSONB |
| `006` | `006_add_doctor_linqmd_credentials.py` | `doctor_linqmd_credentials` table |
| `007` | `007_verbal_intro_file_text.py` | `doctors.verbal_intro_file` → TEXT |
| `008` | `008_create_linq360_schema.py` | PostgreSQL schema `linq360` + `workspace_doctor_dashboard` / `doctor_dashboard` shells |
| `009` | `009_workspace_doctor_dashboard_columns.py` | Rename PK to `appointment_id` + appointment/patient columns on `workspace_doctor_dashboard` |
| `010` | `010_workspace_appointments_json.py` | Add `appointments_json` JSONB array column on `workspace_doctor_dashboard` (head) |

### Tables Created

| Table | Purpose |
|-------|---------|
| `doctors` | Core doctor profile (legacy + 6-block questionnaire) |
| `doctor_identity` | Onboarding identity + status tracking |
| `doctor_details` | Full professional questionnaire (50+ fields) |
| `doctor_media` | Uploaded file references (local/S3) |
| `doctor_status_history` | Immutable audit log |
| `dropdown_options` | Curated dropdown values with approval workflow |
| `users` | RBAC user accounts |
| `linq360.workspace_doctor_dashboard` | Workspace appointments + `appointments_json` array |
| `linq360.doctor_dashboard` | Linq360 doctor dashboard shell (columns TBD) |

> See [database_schema.md](database_schema.md) for full column-level documentation of core tables.
> See [linq360_progress.md](linq360_progress.md) for Linq360 step-by-step progress.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `RuntimeError: Cannot resolve database URL` | Provide a URL via `ALEMBIC_DATABASE_URL`, `-x db_url=`, or `.env` |
| `ModuleNotFoundError: src.app...` | Run from the project root directory (Alembic adds it to `sys.path`) |
| `Target database is not up to date` | Run `alembic upgrade head` first |
| `Can't locate revision` | Check `alembic current` and ensure the versions directory isn't empty |
| `psycopg2 not installed` | Install it: `pip install psycopg2-binary` (needed for sync Alembic operations) |
| `relation "doctors" already exists` on upgrade | `alembic_version` is missing or wrong — use `detect` + `stamp` + `upgrade head` (see above) |
| Migration fails on startup (Docker) | Check `docker compose logs api` for the error. Set `SKIP_MIGRATIONS=true` to start the app while you debug |

---

## Key Design Decisions

1. **Initial migration + incremental revisions** — `001` creates the base schema; later revisions (`002`–`010`) apply incremental DDL. Fresh databases run `upgrade head` once; existing databases may need `stamp` if `alembic_version` was lost.
2. **Async URL auto-conversion** — `env.py` converts `+asyncpg` to `+psycopg2` automatically, so you don't need separate sync/async URLs.
3. **3-tier URL resolution** — CLI flag > env var > app settings. This gives maximum flexibility for different deployment scenarios.
4. **Offline mode support** — You can generate SQL scripts for DBA review without a live database connection.
