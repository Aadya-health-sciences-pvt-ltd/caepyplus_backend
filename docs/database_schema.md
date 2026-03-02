# Database Schema Documentation

**Project:** Doctor Onboarding Smart-Fill API  
**Database:** PostgreSQL (Production) / SQLite (Testing via aiosqlite)  
**ORM:** SQLAlchemy 2.0 (Async)  
**Last Updated:** 2026-03-02  

---

## Overview

This document provides a comprehensive reference for all database tables, columns, data types, and relationships in the Doctor Onboarding system. The schema supports three modes of doctor onboarding: resume upload, voice assistant, and manual CRUD operations.

The entire schema is expressed in a **single Alembic migration** (`001_initial_schema.py`) — no incremental steps.

---

## Table of Contents

1. [doctor_identity](#1-doctor_identity)
2. [doctor_media](#2-doctor_media)
3. [doctor_status_history](#3-doctor_status_history)
4. [dropdown_options](#4-dropdown_options)
5. [users](#5-users)
6. [doctors](#6-doctors) (legacy)
7. [Enumerations](#enumerations)
8. [Relationships](#relationships)
9. [Indexes](#indexes)

---

## 1. `doctor_identity`

**Purpose:** Core doctor identification and contact information table.

**Description:** Stores basic doctor identity, contact details, and onboarding status. Acts as the primary entity for the onboarding pipeline.

| Column Name | Data Type | Constraints | Default | Description |
|------------|-----------|-------------|---------|-------------|
| `id` | `VARCHAR(36)` | PRIMARY KEY | UUID v4 | Unique identifier |
| `doctor_id` | `BIGINT` | UNIQUE, NOT NULL | Auto (sequence) | Numeric doctor ID from `doctor_id_seq` |
| `full_name` | `VARCHAR(200)` | NOT NULL | — | Doctor's full name |
| `email` | `VARCHAR(255)` | UNIQUE, NOT NULL | — | Email address |
| `phone_number` | `VARCHAR(20)` | NOT NULL | — | Contact phone number |
| `onboarding_status` | `ENUM` | NOT NULL | `'pending'` | `pending` \| `submitted` \| `verified` \| `rejected` |
| `status_updated_at` | `TIMESTAMP WITH TZ` | NULLABLE | NULL | When status was last changed |
| `status_updated_by` | `VARCHAR(36)` | NULLABLE | NULL | Admin user ID who updated status |
| `rejection_reason` | `TEXT` | NULLABLE | NULL | Reason for rejection |
| `verified_at` | `TIMESTAMP WITH TZ` | NULLABLE | NULL | Verification completion time |
| `is_active` | `BOOLEAN` | NOT NULL | TRUE | Soft delete flag |
| `registered_at` | `TIMESTAMP WITH TZ` | NOT NULL | UTC NOW | Initial registration timestamp |
| `created_at` | `TIMESTAMP WITH TZ` | NOT NULL | UTC NOW | Row creation timestamp |
| `updated_at` | `TIMESTAMP WITH TZ` | NOT NULL | UTC NOW | Row update timestamp |
| `deleted_at` | `TIMESTAMP WITH TZ` | NULLABLE | NULL | Soft delete timestamp |

**Indexes:**
- Primary Key: `id`
- Unique: `doctor_id`, `email`
- B-tree: `onboarding_status` (fast filtered listing)

**Relationships:**
- ONE-TO-MANY with `doctor_media` (media records)
- ONE-TO-MANY with `doctor_status_history` (audit trail)

---

## 2. `doctor_media`

**Purpose:** Media file references for doctor profiles.

**Description:** Stores references (URIs) and metadata for uploaded files such as profile photos, certificates, achievement images, etc. Actual files are stored in blob storage (local or S3).

| Column Name | Data Type | Constraints | Default | Description |
|------------|-----------|-------------|---------|-------------|
| `media_id` | `VARCHAR(36)` | PRIMARY KEY | UUID v4 | Unique identifier |
| `doctor_id` | `BIGINT` | FK, NOT NULL | — | References `doctor_identity.doctor_id` |
| `field_name` | `VARCHAR(100)` | NULLABLE | NULL | Form field name (e.g., `'profile_photo'`) |
| `media_type` | `VARCHAR(50)` | NOT NULL | — | Type: `'image'`, `'document'`, `'video'` |
| `media_category` | `VARCHAR(50)` | NOT NULL | — | Category: `'profile_photo'`, `'certificate'`, etc. |
| `file_uri` | `TEXT` | NOT NULL | — | Storage URI (local path or S3 URL) |
| `file_name` | `VARCHAR(255)` | NOT NULL | — | Original filename |
| `file_size` | `BIGINT` | NULLABLE | NULL | File size in bytes |
| `mime_type` | `VARCHAR(100)` | NULLABLE | NULL | MIME type (e.g., `'image/jpeg'`) |
| `is_primary` | `BOOLEAN` | NOT NULL | FALSE | Primary file for this category |
| `upload_date` | `TIMESTAMP WITH TZ` | NOT NULL | UTC NOW | Upload timestamp |
| `metadata` | `JSON` | NOT NULL | `{}` | Additional metadata (dimensions, hash, etc.) |

**Indexes:**
- Primary Key: `media_id`
- Index: `doctor_id`
- Foreign Key: `doctor_id` → `doctor_identity.doctor_id` (CASCADE DELETE)

**Relationships:**
- MANY-TO-ONE with `doctor_identity`

---

## 3. `doctor_status_history`

**Purpose:** Immutable audit trail for onboarding status changes.

**Description:** Tracks all status transitions for compliance, debugging, and audit. Every `verify` / `reject` action appends an immutable row via `flush()` so it commits atomically with the status update.

| Column Name | Data Type | Constraints | Default | Description |
|------------|-----------|-------------|---------|-------------|
| `history_id` | `VARCHAR(36)` | PRIMARY KEY | UUID v4 | Unique identifier |
| `doctor_id` | `BIGINT` | FK, NOT NULL | — | References `doctor_identity.doctor_id` |
| `previous_status` | `ENUM` | NULLABLE | NULL | Status before change |
| `new_status` | `ENUM` | NOT NULL | — | Status after change |
| `changed_by` | `VARCHAR(36)` | NULLABLE | NULL | Admin user ID who made change |
| `changed_by_email` | `VARCHAR(255)` | NULLABLE | NULL | Email of who changed |
| `rejection_reason` | `TEXT` | NULLABLE | NULL | Reason if status changed to `'rejected'` |
| `notes` | `TEXT` | NULLABLE | NULL | Additional notes |
| `ip_address` | `VARCHAR(50)` | NULLABLE | NULL | IP address of requester |
| `user_agent` | `TEXT` | NULLABLE | NULL | Browser user agent |
| `changed_at` | `TIMESTAMP WITH TZ` | NOT NULL | UTC NOW | When change occurred |

**Indexes:**
- Primary Key: `history_id`
- Index: `doctor_id`
- Foreign Key: `doctor_id` → `doctor_identity.doctor_id` (CASCADE DELETE)

**Relationships:**
- MANY-TO-ONE with `doctor_identity`

---

## 4. `dropdown_options`

**Purpose:** Curated dropdown values for onboarding form fields with approval workflow.

**Description:** Stores dropdown options (specialisations, qualifications, languages, etc.) for onboarding forms. Supports a 3-status approval workflow: admin/system rows are `approved` immediately; doctor-submitted rows start as `pending` until reviewed. The unique constraint on `(field_name, value)` makes inserts idempotent. Seed data includes ~205 system values across 15 fields.

| Column Name | Data Type | Constraints | Default | Description |
|------------|-----------|-------------|---------|-------------|
| `id` | `INTEGER` | PRIMARY KEY | Auto-increment | Unique identifier |
| `field_name` | `VARCHAR(100)` | NOT NULL, indexed | — | Field identifier (e.g., `'specialty'`, `'qualifications'`) |
| `value` | `VARCHAR(255)` | NOT NULL | — | Option value (unique per `field_name`) |
| `label` | `VARCHAR(255)` | NULLABLE | NULL | Display label (defaults to `value` when not set) |
| `status` | `ENUM` | NOT NULL | `'approved'` | `approved` \| `pending` \| `rejected` |
| `is_system` | `BOOLEAN` | NOT NULL | FALSE | System-seeded rows — cannot be deleted |
| `display_order` | `INTEGER` | NOT NULL | 0 | Sort order within field |
| `submitted_by` | `VARCHAR(36)` | NULLABLE | NULL | User ID who submitted (for PENDING rows) |
| `submitted_by_email` | `VARCHAR(255)` | NULLABLE | NULL | Email of the submitter |
| `reviewed_by` | `VARCHAR(36)` | NULLABLE | NULL | Admin ID who approved/rejected |
| `reviewed_by_email` | `VARCHAR(255)` | NULLABLE | NULL | Email of the reviewer |
| `reviewed_at` | `TIMESTAMP WITH TZ` | NULLABLE | NULL | When the row was reviewed |
| `review_notes` | `TEXT` | NULLABLE | NULL | Admin notes on approval/rejection |
| `created_at` | `TIMESTAMP WITH TZ` | NOT NULL | UTC NOW | Row creation timestamp |
| `updated_at` | `TIMESTAMP WITH TZ` | NOT NULL | UTC NOW | Row update timestamp (auto-updated) |

**Indexes:**
- Primary Key: `id`
- Unique: `(field_name, value)` — idempotent inserts
- Index: `field_name`, `status`

**Supported Fields (15):**

| `field_name` | Description |
|---|---|
| `specialty` | Medical specialisation |
| `sub_specialties` | Sub-specialisation |
| `qualifications` | Academic qualifications / degrees |
| `fellowships` | Fellowship programmes |
| `professional_memberships` | Professional association memberships |
| `languages_spoken` | Languages spoken |
| `age_groups_treated` | Patient age groups |
| `primary_practice_location` | City / practice location |
| `practice_segments` | Practice segment / setting |
| `training_experience` | Notable training & experience |
| `motivation_in_practice` | Motivation in practice |
| `unwinding_after_work` | After-work activities |
| `quality_time_interests` | Personal interests |
| `conditions_treated` | Conditions commonly treated |
| `procedures_performed` | Procedures performed |

---

## 5. `users`

**Purpose:** RBAC user accounts for authentication and authorization.

**Description:** Stores user accounts with role-based access control. Users can be linked to doctors for profile management. The `phone` field is the primary identifier used in JWT.

| Column Name | Data Type | Constraints | Default | Description |
|------------|-----------|-------------|---------|-------------|
| `id` | `SERIAL` | PRIMARY KEY | Auto-increment | Unique identifier |
| `phone` | `VARCHAR(20)` | UNIQUE, NOT NULL | — | Phone number (`+91XXXXXXXXXX` format) |
| `email` | `VARCHAR(255)` | UNIQUE, NULLABLE | NULL | Email address |
| `role` | `VARCHAR(20)` | NOT NULL | `'user'` | `admin` \| `operational` \| `user` |
| `is_active` | `BOOLEAN` | NOT NULL | TRUE | Soft delete flag |
| `doctor_id` | `INTEGER` | FK, NULLABLE | NULL | Link to `doctors.id` (SET NULL on delete) |
| `created_at` | `TIMESTAMP WITH TZ` | NOT NULL | UTC NOW | Creation timestamp |
| `updated_at` | `TIMESTAMP WITH TZ` | NULLABLE | NULL | Update timestamp |
| `last_login_at` | `TIMESTAMP WITH TZ` | NULLABLE | NULL | Last login timestamp |

**Indexes:**
- Primary Key: `id`
- Unique: `phone`, `email`
- Composite: `(role, is_active)`, `(phone, is_active)`
- Foreign Key: `doctor_id` → `doctors.id` (SET NULL on delete)

**Role Definitions:**
- `admin` — Full system access (all admin endpoints)
- `operational` — Limited admin access (onboarding, dropdowns, doctor management)
- `user` — Regular user access (public endpoints only)

---

## 6. `doctors`

**Purpose:** Legacy main doctor entity, also used for bulk CSV uploads and quick profile store.

**Description:** Original doctor table. All profile data lives here. Linked to the `users` table via an optional reverse relationship. New doctors created via CSV bulk upload or OTP sign-up start here.

| Column Name | Data Type | Constraints | Default | Description |
|------------|-----------|-------------|---------|-------------|
| `id` | `SERIAL` | PRIMARY KEY | Auto-increment | Unique identifier |
| `email` | `VARCHAR(100)` | UNIQUE, NULLABLE | NULL | Email address |
| `phone` | `VARCHAR(20)` | UNIQUE, NULLABLE | NULL | Phone number |
| `role` | `VARCHAR(20)` | NOT NULL | `'user'` | `admin` \| `operational` \| `user` |
| `onboarding_status` | `VARCHAR(20)` | NOT NULL | `'pending'` | `pending` \| `submitted` \| `verified` \| `rejected` |
| **Block 1: Professional Identity** |||||
| `full_name` | `VARCHAR(200)` | NULLABLE | NULL | Full name |
| `specialty` | `VARCHAR(100)` | NULLABLE | NULL | Primary specialty |
| `primary_practice_location` | `VARCHAR(100)` | NULLABLE | NULL | Primary city/location |
| `centres_of_practice` | `JSON` | NOT NULL | `[]` | Practice centres |
| `years_of_clinical_experience` | `INTEGER` | NULLABLE | NULL | Clinical experience |
| `years_post_specialisation` | `INTEGER` | NULLABLE | NULL | Post-specialisation years |
| **Block 2: Credentials & Trust Markers** |||||
| `year_of_mbbs` | `INTEGER` | NULLABLE | NULL | MBBS year |
| `year_of_specialisation` | `INTEGER` | NULLABLE | NULL | Specialisation year |
| `fellowships` | `JSON` | NOT NULL | `[]` | Fellowships |
| `qualifications` | `JSON` | NOT NULL | `[]` | Qualifications |
| `professional_memberships` | `JSON` | NOT NULL | `[]` | Professional memberships |
| `awards_academic_honours` | `JSON` | NOT NULL | `[]` | Awards and honours |
| **Block 3: Clinical Focus & Expertise** |||||
| `areas_of_clinical_interest` | `JSON` | NOT NULL | `[]` | Clinical interests |
| `practice_segments` | `VARCHAR(50)` | NULLABLE | NULL | Practice segment |
| `conditions_commonly_treated` | `JSON` | NOT NULL | `[]` | Commonly treated conditions |
| `conditions_known_for` | `JSON` | NOT NULL | `[]` | Known-for conditions |
| `conditions_want_to_treat_more` | `JSON` | NOT NULL | `[]` | Want to treat more |
| **Block 4: The Human Side** |||||
| `training_experience` | `JSON` | NOT NULL | `[]` | Training experiences |
| `motivation_in_practice` | `JSON` | NOT NULL | `[]` | Motivations |
| `unwinding_after_work` | `JSON` | NOT NULL | `[]` | Unwinding activities |
| `recognition_identity` | `JSON` | NOT NULL | `[]` | Recognition items |
| `quality_time_interests` | `JSON` | NOT NULL | `[]` | Quality time interests |
| `quality_time_interests_text` | `TEXT` | NULLABLE | NULL | Quality time text |
| `professional_achievement` | `TEXT` | NULLABLE | NULL | Professional achievement |
| `personal_achievement` | `TEXT` | NULLABLE | NULL | Personal achievement |
| `professional_aspiration` | `TEXT` | NULLABLE | NULL | Professional aspiration |
| `personal_aspiration` | `TEXT` | NULLABLE | NULL | Personal aspiration |
| **Block 5: Patient Value & Choice Factors** |||||
| `what_patients_value_most` | `TEXT` | NULLABLE | NULL | Patient value |
| `approach_to_care` | `TEXT` | NULLABLE | NULL | Care approach |
| `availability_philosophy` | `TEXT` | NULLABLE | NULL | Availability philosophy |
| **Block 6: Content Seed** |||||
| `content_seeds` | `JSON` | NOT NULL | `[]` | Content seeds |
| **Legacy Compatibility Fields** |||||
| `primary_specialization` | `TEXT` | NULLABLE | NULL | Primary specialty (legacy) |
| `years_of_experience` | `INTEGER` | NULLABLE | NULL | Experience years |
| `consultation_fee` | `FLOAT` | NULLABLE | NULL | Consultation fee |
| `consultation_currency` | `VARCHAR(10)` | NULLABLE | `'INR'` | Currency code |
| `medical_registration_number` | `VARCHAR(100)` | NULLABLE | NULL | Registration number |
| `medical_council` | `VARCHAR(200)` | NULLABLE | NULL | Issuing medical council |
| `registration_year` | `INTEGER` | NULLABLE | NULL | Registration year |
| `registration_authority` | `VARCHAR(100)` | NULLABLE | NULL | Registration authority |
| `conditions_treated` | `JSON` | NOT NULL | `[]` | Conditions treated |
| `languages` | `JSON` | NOT NULL | `[]` | Languages spoken |
| `achievements` | `JSON` | NOT NULL | `[]` | Achievements |
| `practice_locations` | `JSON` | NOT NULL | `[]` | Practice locations |
| `onboarding_source` | `VARCHAR(50)` | NULLABLE | NULL | How onboarded: `manual`, `resume`, `voice` |
| `resume_url` | `VARCHAR(500)` | NULLABLE | NULL | Resume file URL |
| `profile_photo` | `VARCHAR(500)` | NULLABLE | NULL | Profile photo URL |
| `verbal_intro_file` | `VARCHAR(500)` | NULLABLE | NULL | Verbal intro file URL |
| `professional_documents` | `JSON` | NOT NULL | `[]` | Professional document URLs |
| `achievement_images` | `JSON` | NOT NULL | `[]` | Achievement image URLs |
| `external_links` | `JSON` | NOT NULL | `[]` | External links |
| `raw_extraction_data` | `JSON` | NULLABLE | NULL | Raw AI extraction output |
| `created_at` | `TIMESTAMP WITH TZ` | NOT NULL | UTC NOW | Row creation timestamp |
| `updated_at` | `TIMESTAMP WITH TZ` | NULLABLE | NULL | Row update timestamp |

**Indexes:**
- Primary Key: `id`
- Unique: `email`, `phone`
- Index: `role`, `onboarding_status`, `onboarding_source`, `medical_registration_number`
- Composite: `(primary_specialization, years_of_experience)`

**Relationships:**
- ONE-TO-ONE with `users` (optional, via `users.doctor_id` → `doctors.id`)

---

## Enumerations

### OnboardingStatus
```python
PENDING = "pending"      # Initial state after profile creation
SUBMITTED = "submitted"  # Doctor submitted for admin review
VERIFIED = "verified"    # Admin approved
REJECTED = "rejected"    # Admin rejected
```


### DropdownOptionStatus
```python
APPROVED = "approved"   # Visible in public dropdowns
PENDING = "pending"     # Awaiting admin review (hidden)
REJECTED = "rejected"   # Admin rejected (never shown)
```

### UserRole
```python
ADMIN = "admin"             # Full system access
OPERATIONAL = "operational" # Limited admin access
USER = "user"               # Regular user access
```

> **Note:** Enums are implemented with `native_enum=False` for SQLite compatibility in tests.

---

## Relationships

### Entity Relationship Diagram

```
doctor_identity (1)
       │
       │ (1)
       │
       ├─────────── (*) doctor_media
       │
       │ (1)
       │
       └─────────── (*) doctor_status_history

doctors (1) ──────────────── (0..1) users
```

**Key Relationships:**

1. **doctor_identity ↔ doctor_media**: One-to-Many (cascade delete)
2. **doctor_identity ↔ doctor_status_history**: One-to-Many (cascade delete)
3. **doctors ↔ users**: One-to-One (optional, via `users.doctor_id` → `doctors.id`, SET NULL)

---

## Indexes

### Performance Indexes

| Table | Index | Type | Purpose |
|-------|-------|------|---------|
| `doctor_identity` | `doctor_id` | UNIQUE | Lookups |
| `doctor_identity` | `email` | UNIQUE | Authentication |
| `doctor_identity` | `onboarding_status` | B-TREE | Fast filtered listing |
| `doctor_media` | `doctor_id` | INDEX | Fetch all media |
| `doctor_status_history` | `doctor_id` | INDEX | Audit trail |
| `dropdown_options` | `field_name` | INDEX | Value lookups |
| `dropdown_options` | `(field_name, value)` | UNIQUE | Deduplication |
| `dropdown_options` | `status` | INDEX | Approval queries |
| `users` | `phone` | UNIQUE | Authentication |
| `users` | `email` | UNIQUE | Lookups |
| `users` | `(role, is_active)` | COMPOSITE | Role queries |
| `users` | `(phone, is_active)` | COMPOSITE | Auth queries |
| `doctors` | `email` | UNIQUE | Lookups |
| `doctors` | `phone` | UNIQUE | Lookups |
| `doctors` | `medical_registration_number` | B-TREE | Fast lookup (not unique at DB level) |
| `doctors` | `(first_name, last_name)` | COMPOSITE | Name search |
| `doctors` | `(primary_specialization, years_of_experience)` | COMPOSITE | Filtering |

---

## Design Notes

1. **Cascade Deletes**: Onboarding relationships (`doctor_media`, `doctor_status_history`) use `CASCADE DELETE`. The `users.doctor_id` FK uses `SET NULL` on delete.
2. **Soft Deletes**: Tables use `is_active` and/or `deleted_at` for soft deletion.
3. **Media stored outside DB**: `doctor_media` stores file URIs (local path or S3 key); binary blobs are never stored in the DB.
4. **Status tracked in two places**: `doctors.onboarding_status` (fast lookup) and `doctor_identity.onboarding_status` (onboarding pipeline) — kept in sync by the status endpoints.
5. **Audit trail**: Every `verify` / `reject` action appends an immutable row to `doctor_status_history` via `flush()` so it commits atomically with the status update.
6. **Race-safe IDs**: `doctor_identity.doctor_id` uses the `doctor_id_seq` PostgreSQL sequence instead of `MAX+1`.
7. **UUIDs**: Primary keys for onboarding tables use UUID v4 for global uniqueness.
8. **JSON Fields**: Used extensively for flexible, schema-less data (arrays, objects).
9. **Timezone Awareness**: All timestamps are `TIMESTAMP WITH TIME ZONE` in UTC.
10. **Enums**: Implemented with `native_enum=False` for SQLite compatibility.

---

## Migration History

The entire schema is expressed in a **single migration file** — no incremental steps.

```bash
# Apply schema (first run and after each deploy)
alembic upgrade head

# Check current revision
alembic current

# Roll back everything
alembic downgrade base
```

| Revision | Description |
|----------|-------------|
| `001_initial_schema` | Complete schema: 6 tables, all indexes, `doctor_id_seq`, admin user seed, ~205 dropdown seed values across 15 fields |

---

**Last Updated:** 2026-03-02  
**Schema Version:** 6.0.0
