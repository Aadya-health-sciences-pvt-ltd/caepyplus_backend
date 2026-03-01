"""Initial schema — complete production migration.

Revision ID: 001
Revises: None
Create Date: 2026-02-26

This is the **single, authoritative** migration for the Doctor Onboarding
Service.  Running ``alembic upgrade head`` on a clean database applies the
entire schema in one step.

Tables created
--------------
- doctors              : Core doctor profile with professional information
- users                : RBAC user management (admin, operational, user)
- doctor_identity      : Onboarding identity and status tracking
- doctor_details       : Comprehensive professional questionnaire data
- doctor_media         : Uploaded media file references
- doctor_status_history: Audit trail for status changes
- dropdown_options     : Dynamic option lists for onboarding form fields
                         (full approval-workflow columns included from creation)

Indexes
-------
- Standard lookup indexes on all tables (see upgrade body for full list)
- B-tree index on ``doctor_identity.onboarding_status`` for filtered listing
- B-tree index on ``dropdown_options.status`` for fast admin-panel filtering

Sequences
---------
- ``doctor_id_seq`` — prevents race conditions on concurrent doctor-identity
  inserts; the application calls ``nextval('doctor_id_seq')`` explicitly so
  that the returned value can be embedded in the same INSERT statement.

Seed data
---------
- Initial admin user   : controlled by SEED_ADMIN_PHONE / SEED_ADMIN_EMAIL
                         env vars (defaults to placeholder values).
- Dropdown options     : ~205 curated values across 15 onboarding form fields
                         (specialty, sub_specialties, qualifications,
                         fellowships, professional_memberships, languages_spoken,
                         age_groups_treated, primary_practice_location,
                         practice_segments, training_experience,
                         motivation_in_practice, unwinding_after_work,
                         quality_time_interests, conditions_treated,
                         procedures_performed).
  All inserts use ``ON CONFLICT DO NOTHING`` — safe to re-run on an already-
  seeded database.
  Every seed row is inserted with:
    status = 'approved', label = value, is_system = TRUE, display_order = 0

dropdown_options columns
------------------------
- id                 : SERIAL primary key
- field_name         : VARCHAR(100), NOT NULL — the onboarding field key
- value              : VARCHAR(255), NOT NULL — the stored/submitted value
- label              : VARCHAR(255), nullable — display label (defaults to value)
- status             : VARCHAR(20),  NOT NULL DEFAULT 'approved' — approval state
                       ('approved' | 'pending' | 'rejected')
- is_system          : BOOLEAN,      NOT NULL DEFAULT FALSE
                       TRUE for curated seed rows (cannot be deleted)
- display_order      : INTEGER,      NOT NULL DEFAULT 0
- submitted_by       : VARCHAR(36),  nullable — user ID who submitted
- submitted_by_email : VARCHAR(255), nullable
- reviewed_by        : VARCHAR(36),  nullable — admin ID who reviewed
- reviewed_by_email  : VARCHAR(255), nullable
- reviewed_at        : TIMESTAMPTZ,  nullable
- review_notes       : TEXT,         nullable
- created_at         : TIMESTAMPTZ,  NOT NULL DEFAULT now()
- updated_at         : TIMESTAMPTZ,  NOT NULL DEFAULT now()

Rollback
--------
``downgrade()`` reverses everything in dependency order:
  sequences → indexes → tables (leaf → root)
"""
from __future__ import annotations

import os as _os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Dropdown seed data — all 15 supported fields
# ---------------------------------------------------------------------------
# fmt: off
_DROPDOWN_SEED: dict[str, list[str]] = {
    "specialty": [
        "Cardiology", "Neurology", "Orthopedics", "Dermatology",
        "Pediatrics", "Gynecology", "Oncology", "Psychiatry",
        "Ophthalmology", "ENT (Ear, Nose & Throat)", "Urology",
        "Gastroenterology", "Pulmonology", "Nephrology", "Endocrinology",
        "Rheumatology", "Hematology", "Infectious Disease", "Radiology",
        "Anesthesiology", "Emergency Medicine", "Family Medicine",
        "Internal Medicine", "General Surgery", "Plastic Surgery",
        "Vascular Surgery", "Neurosurgery", "Cardiothoracic Surgery",
        "Oral & Maxillofacial Surgery", "Dental Surgery",
    ],
    "sub_specialties": [
        "Interventional Cardiology",
        "Paediatric Cardiology",
        "Cardiac Electrophysiology",
        "Neuro-Oncology",
        "Stroke Medicine",
        "Paediatric Neurology",
        "Gynaecological Oncology",
        "Maternal-Fetal Medicine",
        "Reproductive Endocrinology",
        "Paediatric Orthopaedics",
        "Sports Medicine",
        "Hand Surgery",
        "Paediatric Gastroenterology",
        "Hepatology",
        "Inflammatory Bowel Disease",
    ],
    "primary_practice_location": [
        "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai",
        "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Lucknow",
        "Chandigarh", "Kochi", "Bhopal", "Indore", "Nagpur",
        "Coimbatore", "Surat", "Vadodara", "Visakhapatnam", "Patna",
    ],
    "qualifications": [
        "MBBS", "MD", "MS", "DNB", "DM", "MCh",
        "FRCS", "MRCP", "PhD", "MDS", "BDS",
        "DMRD", "DA", "DCH", "DGO", "DLO", "DPM",
        "FCPS", "FICP", "FICS",
    ],
    "fellowships": [
        "Interventional Cardiology", "Electrophysiology",
        "Minimally Invasive Surgery", "Laparoscopic Surgery",
        "Robotic Surgery", "Pediatric Surgery", "Spine Surgery",
        "Joint Replacement", "Oncosurgery", "Transplant Surgery",
        "Fetal Medicine", "Reproductive Medicine", "Neurocritical Care",
        "Pulmonary Critical Care", "Clinical Pharmacology",
    ],
    "professional_memberships": [
        "Indian Medical Association (IMA)",
        "Cardiological Society of India (CSI)",
        "Neurological Society of India (NSI)",
        "Association of Surgeons of India (ASI)",
        "Indian Academy of Pediatrics (IAP)",
        "Indian Society of Gastroenterology (ISG)",
        "Indian Rheumatology Association (IRA)",
        "Indian Radiological and Imaging Association (IRIA)",
        "Indian Orthopaedic Association (IOA)",
        "Indian Psychiatric Society (IPS)",
        "Bombay Medical Association",
        "Delhi Medical Association",
        "Research Society for the Study of Diabetes in India (RSSDI)",
    ],
    "languages_spoken": [
        "English", "Hindi", "Tamil", "Telugu", "Kannada",
        "Malayalam", "Marathi", "Bengali", "Gujarati", "Punjabi",
        "Urdu", "Odia", "Assamese",
    ],
    "age_groups_treated": [
        "Neonates (0–1 month)", "Infants (1–12 months)",
        "Toddlers (1–3 years)", "Children (3–12 years)",
        "Adolescents (12–18 years)", "Adults (18–60 years)",
        "Seniors (60+ years)", "All age groups",
    ],
    "practice_segments": [
        "Private Practice", "Hospital Based", "Academic / Teaching",
        "Corporate Hospital", "Telemedicine", "Rural / Community Health",
        "Government / Public Sector",
    ],
    "training_experience": [
        "Fellowship at AIIMS", "Training at Tata Memorial Hospital",
        "Post-doctoral fellowship at Johns Hopkins",
        "Observership at Cleveland Clinic",
        "International fellowship in the UK",
        "International fellowship in the USA",
        "Exchange program in Germany",
        "Training at Apollo Hospitals",
        "Fellowship at Fortis Healthcare",
        "Advanced surgical training at CMC Vellore",
    ],
    "motivation_in_practice": [
        "Improving patient outcomes", "Advancing medical research",
        "Teaching the next generation of doctors",
        "Making healthcare accessible to all",
        "Reducing unnecessary suffering",
        "Combining technology with compassionate care",
        "Preventive medicine and early diagnosis",
        "Holistic and patient-centred care",
    ],
    "unwinding_after_work": [
        "Reading", "Yoga", "Meditation", "Travelling",
        "Cooking", "Music", "Painting", "Sports",
        "Spending time with family", "Gardening",
        "Cycling", "Swimming", "Photography", "Volunteering",
    ],
    "quality_time_interests": [
        "Family time", "Travel", "Reading", "Fitness",
        "Music", "Cooking", "Art & Craft", "Outdoor activities",
        "Social work", "Spirituality", "Gaming", "Writing",
    ],
    "conditions_treated": [
        "Hypertension",
        "Type 2 Diabetes",
        "Coronary Artery Disease",
        "Heart Failure",
        "Asthma",
        "Chronic Obstructive Pulmonary Disease (COPD)",
        "Thyroid Disorders",
        "Rheumatoid Arthritis",
        "Osteoarthritis",
        "Lower Back Pain",
        "Migraine",
        "Epilepsy",
        "Depression",
        "Anxiety Disorders",
        "Polycystic Ovary Syndrome (PCOS)",
        "Kidney Stones",
        "Gastroesophageal Reflux Disease (GERD)",
        "Irritable Bowel Syndrome (IBS)",
        "Psoriasis",
        "Anaemia",
    ],
    "procedures_performed": [
        "Laparoscopic Cholecystectomy",
        "Appendectomy",
        "Hernia Repair",
        "Coronary Angioplasty (PCI)",
        "Coronary Artery Bypass Grafting (CABG)",
        "Total Knee Replacement",
        "Total Hip Replacement",
        "Spinal Fusion",
        "Cataract Surgery",
        "LASIK Eye Surgery",
        "Tonsillectomy",
        "Hysterectomy",
        "Caesarean Section",
        "Endoscopy (Upper GI)",
        "Colonoscopy",
        "Bronchoscopy",
        "Kidney Dialysis",
        "Chemotherapy Administration",
        "Radiation Therapy",
        "Joint Injection / Aspiration",
    ],
}
# fmt: on


# ===========================================================================
# upgrade
# ===========================================================================

def upgrade() -> None:  # noqa: PLR0915 (too-many-statements)
    # =======================================================================
    # 1. DOCTORS TABLE
    # =======================================================================
    op.create_table(
        "doctors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # Personal details
        sa.Column("title", sa.String(20), nullable=True, comment="Dr., Prof., Prof. Dr."),
        sa.Column("gender", sa.String(20), nullable=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(100), nullable=True, comment="NULL for phone-only signups; filled during onboarding"),
        sa.Column("phone", sa.String(20), nullable=True, comment="International format with + prefix"),
        # Authorization
        sa.Column("role", sa.String(20), nullable=False, server_default="user", comment="admin, operational, user"),
        sa.Column("onboarding_status", sa.String(20), nullable=False, server_default="pending", comment="pending, submitted, verified, rejected"),
        # Block 1: Professional Identity
        sa.Column("full_name", sa.String(200), nullable=True),
        sa.Column("specialty", sa.String(100), nullable=True),
        sa.Column("primary_practice_location", sa.String(100), nullable=True),
        sa.Column("centres_of_practice", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("years_of_clinical_experience", sa.Integer(), nullable=True),
        sa.Column("years_post_specialisation", sa.Integer(), nullable=True),
        # Block 2: Credentials & Trust Markers
        sa.Column("year_of_mbbs", sa.Integer(), nullable=True),
        sa.Column("year_of_specialisation", sa.Integer(), nullable=True),
        sa.Column("fellowships", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("qualifications", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("professional_memberships", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("awards_academic_honours", sa.JSON(), nullable=False, server_default="[]"),
        # Block 3: Clinical Focus & Expertise
        sa.Column("areas_of_clinical_interest", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("practice_segments", sa.String(50), nullable=True),
        sa.Column("conditions_commonly_treated", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("conditions_known_for", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("conditions_want_to_treat_more", sa.JSON(), nullable=False, server_default="[]"),
        # Block 4: The Human Side
        sa.Column("training_experience", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("motivation_in_practice", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("unwinding_after_work", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("recognition_identity", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("quality_time_interests", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("quality_time_interests_text", sa.Text(), nullable=True),
        sa.Column("professional_achievement", sa.Text(), nullable=True),
        sa.Column("personal_achievement", sa.Text(), nullable=True),
        sa.Column("professional_aspiration", sa.Text(), nullable=True),
        sa.Column("personal_aspiration", sa.Text(), nullable=True),
        # Block 5: Patient Value & Choice Factors
        sa.Column("what_patients_value_most", sa.Text(), nullable=True),
        sa.Column("approach_to_care", sa.Text(), nullable=True),
        sa.Column("availability_philosophy", sa.Text(), nullable=True),
        # Block 6: Content Seeds
        sa.Column("content_seeds", sa.JSON(), nullable=False, server_default="[]"),
        # Legacy/compatibility fields
        sa.Column("primary_specialization", sa.Text(), nullable=True),
        sa.Column("years_of_experience", sa.Integer(), nullable=True),
        sa.Column("consultation_fee", sa.Float(), nullable=True),
        sa.Column("consultation_currency", sa.String(10), nullable=True),
        sa.Column("medical_registration_number", sa.String(100), nullable=True),
        sa.Column("medical_council", sa.String(200), nullable=True),
        sa.Column("registration_year", sa.Integer(), nullable=True),
        sa.Column("registration_authority", sa.String(100), nullable=True),
        sa.Column("conditions_treated", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("procedures_performed", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("age_groups_treated", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("sub_specialties", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("areas_of_expertise", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("languages", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("achievements", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("publications", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("practice_locations", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("external_links", sa.JSON(), nullable=False, server_default="[]"),
        # Onboarding metadata
        sa.Column("onboarding_source", sa.String(50), nullable=True, comment="manual, resume, voice"),
        sa.Column("resume_url", sa.String(500), nullable=True),
        sa.Column("profile_photo", sa.String(500), nullable=True),
        sa.Column("verbal_intro_file", sa.String(500), nullable=True),
        sa.Column("professional_documents", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("achievement_images", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("raw_extraction_data", sa.JSON(), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_doctors_id", "doctors", ["id"])
    op.create_index("ix_doctors_first_name", "doctors", ["first_name"])
    op.create_index("ix_doctors_last_name", "doctors", ["last_name"])
    op.create_index("ix_doctors_email", "doctors", ["email"], unique=True)
    op.create_index("ix_doctors_phone", "doctors", ["phone"], unique=True)
    op.create_index("ix_doctors_role", "doctors", ["role"])
    op.create_index("ix_doctors_onboarding_status", "doctors", ["onboarding_status"])
    op.create_index("ix_doctors_medical_registration_number", "doctors", ["medical_registration_number"])
    op.create_index("ix_doctors_onboarding_source", "doctors", ["onboarding_source"])
    op.create_index("ix_doctors_full_name", "doctors", ["first_name", "last_name"])
    op.create_index("ix_doctors_spec_exp", "doctors", ["primary_specialization", "years_of_experience"])

    # =======================================================================
    # 2. USERS TABLE (RBAC)
    # =======================================================================
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("phone", sa.String(20), nullable=False, comment="Phone number with country code"),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="user", comment="admin, operational, user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("doctor_id", sa.Integer(), nullable=True, comment="Optional link to doctor record"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_users_phone", "users", ["phone"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_is_active", "users", ["is_active"])
    op.create_index("ix_users_doctor_id", "users", ["doctor_id"])
    op.create_index("ix_users_role_active", "users", ["role", "is_active"])
    op.create_index("ix_users_phone_active", "users", ["phone", "is_active"])

    # =======================================================================
    # 3. DOCTOR_IDENTITY TABLE
    # =======================================================================
    op.create_table(
        "doctor_identity",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("doctor_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(20), nullable=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone_number", sa.String(20), nullable=False),
        sa.Column("onboarding_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("status_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_updated_by", sa.String(36), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doctor_id"),
        sa.UniqueConstraint("email"),
    )

    op.create_index("ix_doctor_identity_doctor_id", "doctor_identity", ["doctor_id"])
    op.create_index("ix_doctor_identity_email", "doctor_identity", ["email"])
    # B-tree index for admin-panel filtered listing queries (O(log n) vs full scan)
    op.create_index(
        "ix_doctor_identity_onboarding_status",
        "doctor_identity",
        ["onboarding_status"],
        unique=False,
    )

    # =======================================================================
    # 4. DOCTOR_DETAILS TABLE
    # =======================================================================
    op.create_table(
        "doctor_details",
        sa.Column("detail_id", sa.String(36), nullable=False),
        sa.Column("doctor_id", sa.BigInteger(), nullable=False),
        # Block 1: Professional Identity
        sa.Column("full_name", sa.String(200), nullable=True),
        sa.Column("specialty", sa.String(100), nullable=True),
        sa.Column("primary_practice_location", sa.String(100), nullable=True),
        sa.Column("centres_of_practice", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("years_of_clinical_experience", sa.Integer(), nullable=True),
        sa.Column("years_post_specialisation", sa.Integer(), nullable=True),
        # Block 2: Credentials
        sa.Column("year_of_mbbs", sa.Integer(), nullable=True),
        sa.Column("year_of_specialisation", sa.Integer(), nullable=True),
        sa.Column("fellowships", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("qualifications", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("professional_memberships", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("awards_academic_honours", sa.JSON(), nullable=False, server_default="[]"),
        # Block 3: Clinical Focus
        sa.Column("areas_of_clinical_interest", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("practice_segments", sa.String(50), nullable=True),
        sa.Column("conditions_commonly_treated", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("conditions_known_for", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("conditions_want_to_treat_more", sa.JSON(), nullable=False, server_default="[]"),
        # Block 4: Human Side
        sa.Column("training_experience", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("motivation_in_practice", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("unwinding_after_work", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("recognition_identity", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("quality_time_interests", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("quality_time_interests_text", sa.Text(), nullable=True),
        sa.Column("professional_achievement", sa.Text(), nullable=True),
        sa.Column("personal_achievement", sa.Text(), nullable=True),
        sa.Column("professional_aspiration", sa.Text(), nullable=True),
        sa.Column("personal_aspiration", sa.Text(), nullable=True),
        # Block 5: Patient Value
        sa.Column("what_patients_value_most", sa.Text(), nullable=True),
        sa.Column("approach_to_care", sa.Text(), nullable=True),
        sa.Column("availability_philosophy", sa.Text(), nullable=True),
        # Block 6: Content Seeds
        sa.Column("content_seeds", sa.JSON(), nullable=False, server_default="[]"),
        # Legacy compatibility fields
        sa.Column("gender", sa.String(20), nullable=True),
        sa.Column("speciality", sa.String(100), nullable=True),
        sa.Column("sub_specialities", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("areas_of_expertise", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("registration_number", sa.String(100), nullable=True),
        sa.Column("medical_council", sa.String(200), nullable=True),
        sa.Column("registration_year", sa.Integer(), nullable=True),
        sa.Column("registration_authority", sa.String(100), nullable=True),
        sa.Column("consultation_fee", sa.Float(), nullable=True),
        sa.Column("years_of_experience", sa.Integer(), nullable=True),
        sa.Column("conditions_treated", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("procedures_performed", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("age_groups_treated", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("languages_spoken", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("achievements", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("publications", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("practice_locations", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("external_links", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("professional_overview", sa.Text(), nullable=True),
        sa.Column("about_me", sa.Text(), nullable=True),
        sa.Column("professional_tagline", sa.Text(), nullable=True),
        sa.Column("media_urls", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("profile_summary", sa.Text(), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("detail_id"),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctor_identity.doctor_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("doctor_id"),
        sa.UniqueConstraint("registration_number"),
    )

    op.create_index("ix_doctor_details_doctor_id", "doctor_details", ["doctor_id"])

    # =======================================================================
    # 5. DOCTOR_MEDIA TABLE
    # =======================================================================
    op.create_table(
        "doctor_media",
        sa.Column("media_id", sa.String(36), nullable=False),
        sa.Column("doctor_id", sa.BigInteger(), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=True),
        sa.Column("media_type", sa.String(50), nullable=False),
        sa.Column("media_category", sa.String(50), nullable=False),
        sa.Column("file_uri", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("upload_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("media_id"),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctor_identity.doctor_id"], ondelete="CASCADE"),
    )

    op.create_index("ix_doctor_media_doctor_id", "doctor_media", ["doctor_id"])

    # =======================================================================
    # 6. DOCTOR_STATUS_HISTORY TABLE
    # =======================================================================
    op.create_table(
        "doctor_status_history",
        sa.Column("history_id", sa.String(36), nullable=False),
        sa.Column("doctor_id", sa.BigInteger(), nullable=False),
        sa.Column("previous_status", sa.String(20), nullable=True),
        sa.Column("new_status", sa.String(20), nullable=False),
        sa.Column("changed_by", sa.String(36), nullable=True),
        sa.Column("changed_by_email", sa.String(255), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("history_id"),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctor_identity.doctor_id"], ondelete="CASCADE"),
    )

    op.create_index("ix_doctor_status_history_doctor_id", "doctor_status_history", ["doctor_id"])

    # =======================================================================
    # 7. DROPDOWN_OPTIONS TABLE  (includes full approval-workflow columns)
    # =======================================================================
    op.create_table(
        "dropdown_options",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
        # Approval-workflow columns
        sa.Column(
            "label",
            sa.String(255),
            nullable=True,
            comment="Display label; defaults to value when NULL",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="approved",
            comment="approved | pending | rejected",
        ),
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="TRUE for curated seed rows — cannot be deleted",
        ),
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("submitted_by", sa.String(36), nullable=True),
        sa.Column("submitted_by_email", sa.String(255), nullable=True),
        sa.Column("reviewed_by", sa.String(36), nullable=True),
        sa.Column("reviewed_by_email", sa.String(255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("field_name", "value", name="uq_dropdown_field_value"),
    )

    op.create_index("ix_dropdown_options_field_name", "dropdown_options", ["field_name"])
    # Fast admin-panel filtering by approval status
    op.create_index("ix_dropdown_options_status", "dropdown_options", ["status"])

    # =======================================================================
    # 8. SEQUENCE: doctor_id_seq
    # =======================================================================
    # Prevents race conditions on concurrent doctor_identity inserts.
    # The application calls nextval('doctor_id_seq') explicitly so that the
    # returned value is embedded in the INSERT statement — no extra round-trip.
    op.execute("""
        CREATE SEQUENCE doctor_id_seq
            START WITH 1
            INCREMENT BY 1
            NO MINVALUE
            NO MAXVALUE
            CACHE 1;
    """)

    # Advance past any existing rows (COALESCE handles empty-table case)
    op.execute("""
        SELECT setval(
            'doctor_id_seq',
            COALESCE((SELECT MAX(doctor_id) FROM doctor_identity), 1),
            false
        );
    """)

    # Attach as server-side default so raw INSERTs also benefit
    op.execute("""
        ALTER TABLE doctor_identity
            ALTER COLUMN doctor_id
            SET DEFAULT nextval('doctor_id_seq');
    """)

    # =======================================================================
    # SEED: Initial admin user
    # =======================================================================
    # Set SEED_ADMIN_PHONE and SEED_ADMIN_EMAIL env vars before first deploy.
    # The INSERT is idempotent — ON CONFLICT DO NOTHING.
    _admin_phone = _os.environ.get("SEED_ADMIN_PHONE", "+910000000000")
    _admin_email = _os.environ.get("SEED_ADMIN_EMAIL", "admin@linqmd.com")

    op.execute(
        f"""
        INSERT INTO users (phone, email, role, is_active, created_at)
        VALUES ('{_admin_phone}', '{_admin_email}', 'admin', true, now())
        ON CONFLICT DO NOTHING
        """
    )

    # =======================================================================
    # SEED: Dropdown option values (~205 rows across 15 fields)
    # =======================================================================
    # All inserts are idempotent — ON CONFLICT (field_name, value) DO NOTHING.
    # Every seed row is immediately APPROVED and marked is_system=TRUE so that
    # it cannot be accidentally deleted through the admin API.
    for field_name, values in _DROPDOWN_SEED.items():
        for value in values:
            # Escape single quotes in the value
            escaped_value = value.replace("'", "''")
            op.execute(
                f"""
                INSERT INTO dropdown_options
                    (field_name, value, label,
                     status, is_system, display_order,
                     created_at, updated_at)
                VALUES
                    ('{field_name}', '{escaped_value}', '{escaped_value}',
                     'approved', TRUE, 0,
                     now(), now())
                ON CONFLICT (field_name, value) DO NOTHING
                """
            )


# ===========================================================================
# downgrade
# ===========================================================================

def downgrade() -> None:
    """Drop everything in reverse dependency order."""
    # Remove sequence default before dropping the sequence
    op.execute("""
        ALTER TABLE doctor_identity
            ALTER COLUMN doctor_id
            DROP DEFAULT;
    """)
    op.execute("DROP SEQUENCE IF EXISTS doctor_id_seq;")

    op.drop_index("ix_dropdown_options_status", table_name="dropdown_options")
    op.drop_index("ix_dropdown_options_field_name", table_name="dropdown_options")
    op.drop_table("dropdown_options")

    op.drop_index("ix_doctor_status_history_doctor_id", table_name="doctor_status_history")
    op.drop_table("doctor_status_history")

    op.drop_index("ix_doctor_media_doctor_id", table_name="doctor_media")
    op.drop_table("doctor_media")

    op.drop_index("ix_doctor_details_doctor_id", table_name="doctor_details")
    op.drop_table("doctor_details")

    op.drop_index("ix_doctor_identity_onboarding_status", table_name="doctor_identity")
    op.drop_index("ix_doctor_identity_email", table_name="doctor_identity")
    op.drop_index("ix_doctor_identity_doctor_id", table_name="doctor_identity")
    op.drop_table("doctor_identity")

    op.drop_index("ix_users_phone_active", table_name="users")
    op.drop_index("ix_users_role_active", table_name="users")
    op.drop_index("ix_users_doctor_id", table_name="users")
    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_doctors_spec_exp", table_name="doctors")
    op.drop_index("ix_doctors_full_name", table_name="doctors")
    op.drop_index("ix_doctors_onboarding_source", table_name="doctors")
    op.drop_index("ix_doctors_medical_registration_number", table_name="doctors")
    op.drop_index("ix_doctors_onboarding_status", table_name="doctors")
    op.drop_index("ix_doctors_role", table_name="doctors")
    op.drop_index("ix_doctors_phone", table_name="doctors")
    op.drop_index("ix_doctors_email", table_name="doctors")
    op.drop_index("ix_doctors_last_name", table_name="doctors")
    op.drop_index("ix_doctors_first_name", table_name="doctors")
    op.drop_index("ix_doctors_id", table_name="doctors")
    op.drop_table("doctors")
