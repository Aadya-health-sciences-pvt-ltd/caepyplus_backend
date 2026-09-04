# Linq360 Progress

Step-by-step record of Linq360 backend work. The doctor workspace dashboard UI
(today-at-a-glance cards: appointments, requests, messages, payments; and
today’s schedule) is product context only — not implemented yet.

---

## Step 1 — PostgreSQL schema + table shells (done)

**Date:** 2026-09-03

### What we did

1. Created PostgreSQL schema **`linq360`** (separate from the default `public` schema).
2. Created two empty table shells inside that schema:
   - `linq360.workspace_doctor_dashboard` — `id` primary key only
   - `linq360.doctor_dashboard` — `id` primary key only
3. Added dedicated app package so all future Linq360 code lives together:

```
src/app/linq360/
  __init__.py
  models/
    __init__.py
    dashboard.py
  schemas/          # placeholder
  repositories/     # placeholder
  services/         # placeholder
  api/              # placeholder
```

4. Registered models for Alembic metadata (`src/app/models/__init__.py`, `alembic/env.py`).
5. Added Alembic revision **`008`** — `alembic/versions/008_create_linq360_schema.py`.

### Files touched

| File | Change |
|------|--------|
| `src/app/linq360/**` | New package + PK-only models |
| `src/app/models/__init__.py` | Export `WorkspaceDoctorDashboard`, `DoctorDashboard` |
| `alembic/env.py` | Import Linq360 models for metadata |
| `alembic/versions/008_create_linq360_schema.py` | `CREATE SCHEMA` + two tables |
| `docs/linq360_progress.md` | This progress log |
| `docs/alembic_setup.md` | Note revision `008` |

### Apply migration

```bash
python -m alembic upgrade head
# or
python scripts/migrate.py upgrade head
```

### Explicitly out of scope for Step 1

- Business columns on either table
- Repositories, services, API endpoints
- Appointment / request / message / payment features

---

## Step 2 — `workspace_doctor_dashboard` columns (done)

**Date:** 2026-09-03

### What we did

1. Renamed PK `id` → `appointment_id` on `linq360.workspace_doctor_dashboard`.
2. Added business columns (all NOT NULL):

| Column | Type |
|--------|------|
| `appointment_id` | `INTEGER` autoincrement PK |
| `patient_meta_code` | `VARCHAR(255)` |
| `appointment_type` | enum: `REQUEST`, `BOOKING`, `CALL` (stored as VARCHAR) |
| `patient_name` | `VARCHAR(255)` |
| `first_name` | `VARCHAR(255)` |
| `last_name` | `VARCHAR(255)` |
| `consultation_type` | enum: `in-person`, `teleconsultation` (stored as VARCHAR) |
| `time_slot` | `VARCHAR(255)` |

3. Added Linq360 enums in `src/app/linq360/models/enums.py`.
4. Added Alembic revision **`009`** — `alembic/versions/009_workspace_doctor_dashboard_columns.py`.
5. Left `doctor_dashboard` unchanged (`id` PK shell only).

### Files touched

| File | Change |
|------|--------|
| `src/app/linq360/models/enums.py` | `AppointmentType`, `ConsultationType` |
| `src/app/linq360/models/dashboard.py` | Full `WorkspaceDoctorDashboard` columns |
| `src/app/linq360/models/__init__.py` | Export enums |
| `alembic/versions/009_workspace_doctor_dashboard_columns.py` | Rename PK + add columns |
| `docs/linq360_progress.md` | Step 2 log |
| `docs/alembic_setup.md` | Note revision `009` |

### Apply migration

```bash
python -m alembic upgrade head
```

---

## Step 3 — `appointments_json` column (done)

**Date:** 2026-09-03

### What we did

1. Added **`appointments_json`** (`JSONB` / `JSON`) at the end of `linq360.workspace_doctor_dashboard`.
   - NOT NULL, server default `[]`
   - Always store an **array** of appointment objects (one booking = `[ {...} ]`; multiple = longer array)
2. No API in this step.
3. Added folder pieces for the JSON shape:

```
src/app/linq360/
  schemas/dashboard.py
  data/workspace_appointments.sample.json
```

4. Added Alembic revision **`010`** — `alembic/versions/010_workspace_appointments_json.py`.
5. Left `doctor_dashboard` unchanged (`id` PK shell only).

### Example `appointments_json` value

```json
[
  {
    "patient_meta_code": "PAT-001",
    "appointment_type": "BOOKING",
    "patient_name": "Rajesh Kumar",
    "first_name": "Rajesh",
    "last_name": "Kumar",
    "consultation_type": "in-person",
    "time_slot": "10:30 AM"
  },
  {
    "patient_meta_code": "PAT-001",
    "appointment_type": "REQUEST",
    "patient_name": "Rajesh Kumar",
    "first_name": "Rajesh",
    "last_name": "Kumar",
    "consultation_type": "teleconsultation",
    "time_slot": "02:00 PM"
  }
]
```

### Files touched

| File | Change |
|------|--------|
| `src/app/linq360/models/dashboard.py` | `appointments_json` column |
| `alembic/versions/010_workspace_appointments_json.py` | Add column |
| `src/app/linq360/schemas/dashboard.py` | Pydantic item/payload shapes |
| `src/app/linq360/data/workspace_appointments.sample.json` | Sample array |
| `docs/linq360_progress.md` | Step 3 log |
| `docs/alembic_setup.md` | Note revision `010` |

### Apply migration

```bash
python -m alembic upgrade head
```

---

## Step 4 — trim `workspace_doctor_dashboard` columns (done)

**Date:** 2026-09-04

### What we did

Kept only four columns on `linq360.workspace_doctor_dashboard`:

| Column | Type |
|--------|------|
| `appointment_id` | `INTEGER` autoincrement PK |
| `workspace_id` | `INTEGER` NOT NULL, indexed |
| `user_id` | `INTEGER` NOT NULL, indexed |
| `appointments_json` | JSONB (shape later changed to a single object in Step 5) |

Dropped flat columns (`patient_meta_code`, `appointment_type`, `patient_name`, `first_name`, `last_name`, `consultation_type`, `time_slot`). Appointment details stay in `appointments_json`.

No FKs (no workspace table yet; linq360 stays independent of `public.users`). Alembic **`011`**. Pydantic sample JSON shape unchanged.

### Apply migration

```bash
python -m alembic upgrade head
```

---

## Step 5 — `appointments_json` is a single object (done)

**Date:** 2026-09-04

`appointments_json` is no longer an array. Each row stores **one JSON object**.

Example:

```json
{
  "patient_meta_code": "PAT-001",
  "appointment_type": "BOOKING",
  "patient_name": "Rajesh Kumar",
  "first_name": "Rajesh",
  "last_name": "Kumar",
  "consultation_type": "in-person",
  "time_slot": "10:30 AM"
}
```

Alembic **`012`** converts existing arrays by taking the first element (or `{}` if empty) and sets the server default to `{}`.

### Apply migration

```bash
python -m alembic upgrade head
```

---

## Step 6 — `doctor_dashboard` columns (pending)

Waiting on column definitions for `doctor_dashboard`.

---

## Later steps (not started)

- Repositories / services
- API endpoints under `src/app/linq360/api/`
- Dashboard aggregation and schedule data
- Regenerate / extend `docs/database_schema.md` for `linq360` tables when both tables have columns
