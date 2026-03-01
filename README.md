# 🏥 Doctor Onboarding Smart-Fill API 

<div align="center">

![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.12+-green.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)
![License](https://img.shields.io/badge/license-MIT-yellow.svg)

**Production-grade FastAPI backend for AI-powered doctor onboarding with resume parsing and voice registration**

[Features](#-features) • [Architecture](#-architecture) • [Quick Start](#-quick-start) • [API Reference](#-api-reference) • [Development](#-development-guide)

</div>

----

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Architecture](#-architecture)
- [Project Structure](#-project-structure)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [API Reference](#-api-reference)
  - [Authentication](#authentication)
  - [Doctor Management](#doctor-management)
  - [Bulk Doctor CSV Upload](#bulk-doctor-csv-upload-admin--operational-role)
  - [Admin Verification & Email Notifications](#admin-verification--email-notifications)
  - [Dropdown Options (Speciality & Other Fields)](#dropdown-options-speciality--other-fields)
  - [Voice Onboarding](#voice-onboarding)
  - [Admin User Management](#admin-user-management-admin-role-only)
- [Database Schema](#-database-schema)
- [Voice Onboarding Flow](#-voice-onboarding-flow)
- [Development Guide](#-development-guide)
- [Testing](#-testing)
- [CI/CD Pipeline](#️-cicd-pipeline)
- [Deployment](#-deployment)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)

---

## 🎯 Overview

Doctor Onboarding Smart-Fill is a **production-grade FastAPI microservice** that streamlines doctor registration for healthcare platforms. It offers three intelligent onboarding modes powered by Google Gemini AI:

1. **📄 Resume Upload** - Upload PDF/Image CVs and AI extracts structured professional data
2. **🎤 Voice Assistant** - Natural conversational AI collects registration details via speech
3. **📝 Manual CRUD** - RESTful API for traditional form-based data entry

Built with modern Python patterns, comprehensive type safety, and enterprise-grade architecture.

---

## ✨ Features

### Core Features
| Feature | Description |
|---------|-------------|
| **🤖 AI Resume Parsing** | Extract doctor information from PDF/image resumes using Gemini Vision API |
| **🎤 Voice Onboarding** | Conversational AI assistant for hands-free data collection |
| **🔄 Smart Auto-fill** | Extracted data automatically populates registration forms |
| **✅ Real-time Validation** | End-to-end validation with Pydantic schemas |
| **📁 Multi-format Support** | PDF, PNG, JPG, JPEG uploads (up to 10MB) |
| **📊 Bulk CSV Upload** | Admin/operational users upload up to 500 doctors at once via a two-phase validate → confirm workflow |
| **📧 Email Notifications** | Admin-triggered verification/rejection emails with editable templates loaded from YAML config |

### Technical Features
| Feature | Description |
|---------|-------------|
| **⚡ High Performance** | Async FastAPI with ORJSON responses and connection pooling |
| **🔒 Type Safety** | 100% type-hinted Python with Pydantic V2 validation |
| **📚 OpenAPI 3.0** | Auto-generated Swagger UI with comprehensive documentation |
| **🗄️ Modern Database** | SQLAlchemy 2.0 async ORM with PostgreSQL (production); SQLite in-memory for tests only |
| **🔄 Session Management** | In-memory voice session tracking with automatic cleanup |
| **🏥 Health Checks** | Kubernetes-ready health, readiness, and liveness probes |
| **📊 Structured Logging** | JSON logging with context and correlation IDs |
| **🐳 Container Ready** | Multi-stage Docker builds with optimized images |

---

## 🛠 Tech Stack

### Backend (FastAPI Microservice)
| Technology | Version | Purpose |
|------------|---------|---------|
| **FastAPI** | 0.115+ | High-performance async web framework |
| **Python** | 3.12+ | Runtime with modern async/await patterns |
| **SQLAlchemy** | 2.0.36+ | Async ORM with modern syntax |
| **Pydantic** | 2.10+ | Data validation and serialization |
| **Google Gemini** | 1.0+ | AI for extraction & conversation (new SDK) |
| **Uvicorn** | 0.32+ | ASGI server with performance optimizations |
| **PostgreSQL** | 16+ | Production database (asyncpg driver) |
| **SQLite** | - | Test-suite only (in-memory `aiosqlite`; NOT used in production/dev) |
| **Alembic** | 1.14+ | Database migrations |
| **Structlog** | 24.4+ | Structured logging |
| **ORJSON** | 3.10+ | Fast JSON serialization |

### Development & Quality
| Technology | Version | Purpose |
|------------|---------|---------|
| **Ruff** | 0.8+ | Fast Python linter and formatter |
| **MyPy** | 1.13+ | Static type checker |
| **Pytest** | 8.3+ | Testing framework with async support |
| **Pre-commit** | 4.0+ | Git hooks for code quality |

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL LAYER                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    REST API / OpenAPI 3.0                       │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │   │
│  │  │   /doctors   │  │ /onboarding  │  │    /voice/*          │   │   │
│  │  │   (CRUD)     │  │ (extraction) │  │  (conversation)      │   │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ HTTP/REST
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            API LAYER                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      FastAPI Endpoints                            │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │   │
│  │  │ DoctorsAPI   │  │ OnboardingAPI│  │ VoiceAPI             │   │   │
│  │  │ Controller   │  │ Controller   │  │ Controller           │   │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Dependency Injection
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           SERVICE LAYER                                 │
│  ┌──────────────────┐  ┌───────────────────┐  ┌────────────────────┐   │
│  │ DoctorRepository │  │ ExtractionService │  │ VoiceOnboardingSvc │   │
│  │ (Data Access)    │  │ (Gemini Vision)   │  │ (Gemini Chat)      │   │
│  └──────────────────┘  └───────────────────┘  └────────────────────┘   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
           ┌──────────────┐                 ┌─────────────────┐
           │ PostgreSQL   │                 │  Google Gemini  │
           │ Database     │                 │  AI API         │
           │ (Doctors,    │                 │  (Vision + Chat)│
           │Qualifications)│                 └─────────────────┘
           └──────────────┘
```

### Clean Architecture Principles

- **Dependency Inversion**: Services depend on abstractions (repositories, external APIs)
- **Single Responsibility**: Each layer has one clear purpose
- **Interface Segregation**: Focused, minimal interfaces
- **Open/Closed**: Extensible without modifying existing code

### Data Flow Patterns

**Resume Extraction Flow:**
```
Upload PDF/Image → Validate → Gemini Vision API → Parse JSON → Validate Schema → Return Structured Data
```

**Voice Onboarding Flow:**
```
Start Session → User Speech → Gemini Chat API → Extract Fields → Update Session → Generate Response → Continue Loop
```

**CRUD Operations:**
```
Request → Validate → Repository → Database → Response
```

**Bulk CSV Upload Flow (two-phase):**
```
Phase 1 (validate):  Upload CSV → Decode UTF-8 → Check Headers → Validate All Rows → Return Error List (no DB)
Phase 2 (confirm):   Upload CSV → Re-validate Gate → Per-row Savepoint → flush() each row → Final commit → Response
```

---

## 📁 Project Structure

```
caepy_plus_back_end/
├── src/app/                          # Main application package
│   ├── main.py                       # FastAPI app factory + middleware
│   ├── api/v1/
│   │   ├── __init__.py               # Versioned router (prefix /api/v1)
│   │   └── endpoints/
│   │       ├── admin_users.py        # Admin user management (RBAC)
│   │       ├── doctors.py            # Doctor CRUD endpoints
│   │       ├── health.py             # Health / liveness / readiness probes
│   │       ├── onboarding.py         # Doctor onboarding status endpoints
│   │       ├── onboarding_admin.py   # Admin onboarding dashboard endpoints
│   │       ├── otp.py                # OTP auth + JWT issuance
│   │       └── voice.py              # Voice conversation endpoints
│   ├── core/
│   │   ├── config.py                 # Pydantic BaseSettings (12-factor)
│   │   ├── doctor_utils.py           # Shared synthesise_identity() helper
│   │   ├── exceptions.py             # Custom exception hierarchy
│   │   ├── firebase_config.py        # Firebase token verification
│   │   ├── prompts.py                # YAML prompt loader
│   │   ├── rbac.py                   # RBAC dependencies (AdminUser, AdminOrOperationalUser)
│   │   ├── responses.py              # Standardised API response shapes
│   │   └── security.py               # JWT decode + require_authentication dependency
│   ├── db/
│   │   └── session.py                # Async SQLAlchemy engine + get_db()
│   ├── models/
│   │   ├── doctor.py                 # doctors table
│   │   ├── enums.py                  # UserRole enum
│   │   ├── onboarding.py             # doctor_identity / details / media / history
│   │   └── user.py                   # users table (RBAC)
│   ├── repositories/
│   │   ├── doctor_repository.py      # Doctor data access layer
│   │   ├── onboarding_repository.py  # Onboarding data access layer
│   │   └── user_repository.py        # User RBAC data access layer
│   ├── schemas/
│   │   ├── auth.py                   # OTP request/verify schemas
│   │   ├── doctor.py                 # Doctor DTOs (create/update/response)
│   │   ├── onboarding.py             # Onboarding DTOs
│   │   ├── user.py                   # User DTOs
│   │   └── voice.py                  # Voice session schemas
│   ├── services/
│   │   ├── blob_storage_service.py   # Local / S3 file storage
│   │   ├── extraction_service.py     # Resume parsing (Gemini Vision)
│   │   ├── gemini_service.py         # Gemini AI singleton wrapper
│   │   ├── otp_service.py            # OTP generation + Redis/in-memory store
│   │   └── voice_service.py          # Voice conversation state machine
│   └── static/
│       └── doctor_bulk_upload_template.csv  # Bundled CSV template (48 columns, 2 sample rows)
├── alembic/                          # Database migrations (sole schema owner)
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py     # Single complete schema (all tables, indexes, sequences, seeds)
├── config/
│   └── prompts.yaml                  # External AI prompt configuration
├── tests/
│   ├── conftest.py                   # Async engine, db_session, client fixtures
│   ├── unit/
│   │   ├── test_auth_schemas.py      # _normalise_indian_mobile, OTP schemas
│   │   ├── test_jwt_helpers.py       # encode/decode/expiry/tamper
│   │   └── test_doctor_utils.py      # synthesise_identity()
│   ├── integration/
│   │   ├── test_doctor_repository.py
│   │   ├── test_onboarding_repository.py
│   │   ├── test_user_repository.py   # update_fields atomicity
│   │   └── test_otp_endpoints.py
│   ├── api/                          # HTTP endpoint tests
│   ├── core/                         # Core module tests
│   └── services/                     # Service-layer tests
├── pyproject.toml                    # Project metadata + pytest config
├── Dockerfile                        # Multi-stage production image (builder + production stages)
├── docker-compose.yml                # Full dev stack (API + PostgreSQL + Redis + optional pgAdmin)
├── entrypoint.sh                     # Container startup: wait-for-DB → alembic upgrade head → uvicorn
├── .dockerignore                     # Excludes venv/, .env, __pycache__, tests/, etc. from image
├── .env.example                      # Environment variable template (no real secrets)
└── README.md
```

---

## 🚀 Quick Start (From Scratch)

> **Complete setup guide for someone starting fresh with this codebase**

### Prerequisites

> ⚠️ **IMPORTANT**: This project requires **Python 3.10 or higher**. Python 3.9 and below are NOT supported due to modern type hint syntax (`str | tuple` instead of `Union[str, tuple]`).

| Requirement | Version | Installation |
|-------------|---------|--------------|
| **Python** | **3.10, 3.11, or 3.12** (3.12 recommended) | [Download](https://www.python.org/downloads/) or `brew install python@3.12` |
| **PostgreSQL** | 15+ or 16+ | `brew install postgresql@15` (macOS) |
| **pip** | Latest | Comes with Python |

---

### Step 1: Extract & Navigate

```bash
# If you received a zip file
unzip caepy_plus_backend.zip
cd caepy_plus_backend
```

---

### Step 2: Verify Python Version

```bash
# Check Python version (MUST be 3.10+)
python3 --version

# If you have Python 3.9 or below, install a newer version:
brew install python@3.12        # macOS
# or download from https://www.python.org/downloads/

# Verify you have Python 3.10+
python3.12 --version  # Should show 3.12.x
# OR
python3.11 --version  # Should show 3.11.x
# OR  
python3.10 --version  # Should show 3.10.x
```

---

### Step 3: Create Python Virtual Environment

```bash
# Create virtual environment with Python 3.10+ (use the version you verified above)
python3.12 -m venv venv     # Recommended: Python 3.12
# OR
# python3.11 -m venv venv   # Python 3.11 also works
# OR
# python3.10 -m venv venv   # Python 3.10 minimum

# Activate it
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

# Verify the venv is using Python 3.10+
python3 --version               # Should show 3.10+ inside venv
```

---

### Step 4: Install Dependencies

```bash
# Install application + all dev dependencies (pytest, ruff, mypy, etc.)
pip install -e ".[dev]"

# Or install only runtime dependencies (production):
pip install .
```

---

### Step 5: Install & Start PostgreSQL

#### macOS (Homebrew)
```bash
# Install PostgreSQL 15
brew install postgresql@15

# Start PostgreSQL service
brew services start postgresql@15

# Verify it's running
brew services list | grep postgres
# Should show: postgresql@15 started
```

#### Ubuntu/Debian
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

#### Windows
Download and install from [postgresql.org](https://www.postgresql.org/download/windows/)

---

### Step 6: Create Database & User

#### macOS (PostgreSQL 15)
```bash
/opt/homebrew/opt/postgresql@15/bin/psql -U $(whoami) -d postgres << 'EOF'
-- Create user
CREATE USER your_db_user WITH PASSWORD 'your_db_password';

-- Create database
CREATE DATABASE doctor_onboarding OWNER your_db_user;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE doctor_onboarding TO your_db_user;

-- Connect and grant schema access
\c doctor_onboarding
GRANT ALL ON SCHEMA public TO your_db_user;
EOF
```

#### Linux/Windows (using psql)
```bash
sudo -u postgres /opt/homebrew/opt/postgresql@15/bin/psql << 'EOF'
CREATE USER your_db_user WITH PASSWORD 'your_db_password';
CREATE DATABASE doctor_onboarding OWNER your_db_user;
GRANT ALL PRIVILEGES ON DATABASE doctor_onboarding TO your_db_user;
\c doctor_onboarding
GRANT ALL ON SCHEMA public TO your_db_user;
EOF
```

---

### Step 7: Populate .env

Copy the template and fill in **all required values**:

```bash
cp .env.example .env
```

Minimum required keys for the service to start:

```properties
# Database
DATABASE_URL=postgresql+asyncpg://your_db_user:your_db_password@localhost:5432/doctor_onboarding

# JWT signing key — generate with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your-minimum-32-character-secret-key

# Google Gemini AI — https://aistudio.google.com/app/apikey
GOOGLE_API_KEY=your-google-gemini-api-key
GEMINI_MODEL=gemini-2.5-flash

# Firebase (for Google Sign-In)
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_WEB_API_KEY=your-firebase-web-api-key

# SMS OTP gateway (onlysms.co.in)
SMS_USER_ID=your-sms-user-id
SMS_USER_PASS=your-sms-password
SMS_GSM_ID=your-gsm-sender-id
SMS_PE_ID=your-pe-id
SMS_TEMPLATE_ID=your-template-id
```

> ⚠️ **Never commit `.env` to version control.** Use `.env.example` as the template only.

---

### Step 8: Run Database Migrations & Start the Server

```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Apply all migrations (creates all tables — required before first start)
./venv/bin/alembic upgrade head

# Start the server in development mode
./venv/bin/uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000
```

> ⚠️ **Schema is managed exclusively by Alembic.** Tables are NOT auto-created on startup. Always run `alembic upgrade head` before the first launch and after any migration is added.

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

---

### Step 9: Verify Everything Works

```bash
# Liveness probe — confirms app is running (no auth required)
curl http://localhost:8000/api/v1/live
# → {"status": "alive"}

# Readiness probe — confirms DB connection is healthy
curl http://localhost:8000/api/v1/ready
# → {"status": "ready"}

# Full health check — DB + AI service status
curl http://localhost:8000/api/v1/health
```

Expected response for `/api/v1/health`:
```json
{
  "status": "healthy",
  "service": "doctor-onboarding-service",
  "checks": {
    "database": {"status": "healthy"},
    "ai_service": {"status": "healthy"}
  }
}
```

---

### Step 10: Access the API

| URL | Description |
|-----|-------------|
| http://localhost:8000/docs | Swagger UI (Interactive API docs) |
| http://localhost:8000/redoc | ReDoc (Alternative docs) |
| http://localhost:8000/api/v1/health | Health check endpoint |

---

### 🎉 Quick Start Summary (Copy-Paste Commands)

#### Option A — Local Python (without Docker)

```bash
# === ONE-TIME SETUP ===

# 1. Extract and enter directory
cd caepy_plus_backend

# 2. Verify Python version (MUST be 3.10+)
python3 --version
# If 3.9 or below, install Python 3.12:
brew install python@3.12

# 3. Create & activate virtual environment with Python 3.10+
python3.12 -m venv venv  # Use python3.12, python3.11, or python3.10
source venv/bin/activate

# 4. Install dependencies (includes dev tools)
pip install -e ".[dev]"

# 5. Install PostgreSQL (macOS)
brew install postgresql@15
brew services start postgresql@15

# 6. Create database
/opt/homebrew/opt/postgresql@15/bin/psql -U $(whoami) -d postgres -c "
CREATE USER your_db_user WITH PASSWORD 'your_db_password';
CREATE DATABASE doctor_onboarding OWNER your_db_user;
GRANT ALL PRIVILEGES ON DATABASE doctor_onboarding TO your_db_user;
"

# 7. Grant schema permissions
/opt/homebrew/opt/postgresql@15/bin/psql -U your_db_user -d doctor_onboarding -c "GRANT ALL ON SCHEMA public TO your_db_user;"

# 8. Populate .env (copy template and fill in required values)
cp .env.example .env   # then edit .env with real keys

# 9. Run database migrations (REQUIRED before first start)
./venv/bin/alembic upgrade head

# === START SERVER ===
./venv/bin/uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000

# === VERIFY ===
curl http://localhost:8000/api/v1/live    # → {"status": "alive"}
curl http://localhost:8000/api/v1/ready   # → {"status": "ready"}
```

#### Option B — Docker (recommended for teams / zero local setup)

```bash
# 1. Copy env template and fill in required secrets
cp .env.example .env
# Edit .env: set GOOGLE_API_KEY, SMS_USER_ID, SMS_USER_PASS, SECRET_KEY, PGADMIN_PASSWORD

# 2. Build and start the full stack (API + PostgreSQL + Redis)
docker compose up --build

# Migrations run automatically inside the container before the app starts.

# === VERIFY ===
curl http://localhost:8000/api/v1/live    # → {"status": "alive"}
curl http://localhost:8000/api/v1/ready   # → {"status": "ready"}

# === STOP ===
docker compose down        # keeps volumes (DB data preserved)
docker compose down -v     # removes volumes (fresh start)

# === PGADMIN (optional DB GUI) ===
docker compose --profile tools up
# Visit http://localhost:5050  (login: PGADMIN_EMAIL / PGADMIN_PASSWORD from .env)
# Server: host=db  port=5432  db=doctor_onboarding  user=postgres  pass=postgres
```

---

### Troubleshooting Quick Start

| Problem | Solution |
|---------|----------|
| **`TypeError: unsupported operand type(s) for \|`** | **🔴 CRITICAL: You're using Python 3.9 or below. This project requires Python 3.10+. Delete venv and recreate with Python 3.10+: `rm -rf venv && python3.12 -m venv venv`** |
| `command not found: psql` | Use full path: `/opt/homebrew/opt/postgresql@15/bin/psql` |
| `role "your_db_user" already exists` | User exists, skip creation |
| `database "doctor_onboarding" already exists` | Database exists, skip creation |
| `Address already in use (port 8000)` | Kill existing process: `lsof -ti:8000 \| xargs kill -9` |
| `ModuleNotFoundError` | Activate venv: `source venv/bin/activate` |
| `Connection refused` to database | Start PostgreSQL: `brew services start postgresql@15` |
| `python3.12: command not found` | Install Python 3.12: `brew install python@3.12` |
| `alembic: command not found` | Use full path: `./venv/bin/alembic upgrade head` |
| `FIREBASE_WEB_API_KEY not set` | Add Firebase vars to `.env` (see Configuration section) |
| `/api/v1/ready` → `role "your_db_user" does not exist` | `DATABASE_URL` in `.env` still has placeholder values. Replace `your_db_user` and `your_db_password` with real credentials |
| Swagger UI at `/docs` is blank | CSP blocks scripts in production. Make sure `APP_ENV` ≠ `production` during local dev |
| `CORS error` in browser when calling API | If `CORS_ORIGINS=*`, set `CORS_ALLOW_CREDENTIALS=false`. Browser rejects wildcard origin + credentials together |

---

## ⚙️ Configuration

### Current Configuration (.env)

Copy `.env.example` → `.env` and fill in the required values. Full reference:

```properties
# ── Application ───────────────────────────────────────────────
APP_NAME=doctor-onboarding-service
APP_VERSION=2.0.0
APP_ENV=development          # development | production
DEBUG=true

# ── Server ────────────────────────────────────────────────────
HOST=0.0.0.0
PORT=8000

# ── Security (REQUIRED) ───────────────────────────────────────
# Generate: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your-minimum-32-character-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# ── Database (REQUIRED) ───────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://your_db_user:your_db_password@localhost:5432/doctor_onboarding

# ── Google Gemini AI (REQUIRED) ───────────────────────────────
# Get key: https://aistudio.google.com/app/apikey
GOOGLE_API_KEY=your-google-gemini-api-key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_TEMPERATURE=0.1
GEMINI_MAX_TOKENS=4096

# ── Firebase (REQUIRED for Google Sign-In) ────────────────────
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_WEB_API_KEY=your-firebase-web-api-key

# ── SMS OTP Gateway (REQUIRED for OTP auth) ───────────────────
SMS_API_BASE_URL=https://onlysms.co.in/api/otp.aspx
SMS_USER_ID=your-sms-user-id
SMS_USER_PASS=your-sms-password
SMS_GSM_ID=your-gsm-sender-id
SMS_PE_ID=your-pe-id
SMS_TEMPLATE_ID=your-template-id

# ── OTP Settings ──────────────────────────────────────────────
OTP_LENGTH=6
OTP_EXPIRY_SECONDS=300
OTP_MAX_ATTEMPTS=3

# ── Redis (for OTP store — falls back to in-memory if disabled) ──
REDIS_URL=redis://localhost:6379/0
REDIS_ENABLED=true

# ── Blob Storage ──────────────────────────────────────────────
STORAGE_BACKEND=local        # local | s3
BLOB_STORAGE_PATH=./blob_storage
BLOB_BASE_URL=/api/v1/blobs

# AWS S3 (when STORAGE_BACKEND=s3)
# AWS_ACCESS_KEY_ID=your_access_key_here
# AWS_SECRET_ACCESS_KEY=your_secret_key_here
# AWS_REGION=us-east-1
# AWS_S3_BUCKET=your-bucket-name
# AWS_S3_PREFIX=doctors
# AWS_S3_USE_SIGNED_URLS=false
# AWS_S3_SIGNED_URL_EXPIRY=3600

# ── Email / SMTP (for verification & rejection notifications) ──
EMAIL_ENABLED=false               # Set true to activate email sending
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587                     # 587=STARTTLS  465=SSL  25=plain
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password   # Gmail: use App Password, not account password
SMTP_USE_TLS=true                 # STARTTLS on port 587
SMTP_USE_SSL=false                # Implicit SSL on port 465 (mutually exclusive with TLS)
EMAIL_FROM_ADDRESS=noreply@linqmd.com
EMAIL_FROM_NAME=LinQMD Platform
EMAIL_TEMPLATES_PATH=config/email_templates.yaml
EMAIL_TIMEOUT_SECONDS=10
```

### Email Provider Quick-Reference

| Provider | `SMTP_HOST` | `SMTP_PORT` | `SMTP_USE_TLS` | `SMTP_USE_SSL` | Notes |
|----------|-------------|-------------|----------------|----------------|-------|
| **Gmail** | `smtp.gmail.com` | `587` | `true` | `false` | Requires [App Password](https://support.google.com/accounts/answer/185833) |
| **Gmail SSL** | `smtp.gmail.com` | `465` | `false` | `true` | Implicit SSL |
| **SendGrid** | `smtp.sendgrid.net` | `587` | `true` | `false` | `SMTP_USERNAME=apikey`, password = SG key |
| **AWS SES** | `email-smtp.<region>.amazonaws.com` | `587` | `true` | `false` | IAM SMTP credentials |
| **Mailgun** | `smtp.mailgun.org` | `587` | `true` | `false` | SMTP credentials from Mailgun dashboard |

> **Template customisation** — Edit `config/email_templates.yaml` to change email copy.
> Changes take effect on the next server restart (templates are cached in memory).

### Database Credentials

| Parameter | Value |
|-----------|-------|
| **Host** | `localhost` |
| **Port** | `5432` |
| **Database** | `doctor_onboarding` |
| **Username** | `your_db_user` |
| **Password** | `your_db_password` |
| **Connection URL** | `postgresql+asyncpg://your_db_user:your_db_password@localhost:5432/doctor_onboarding` |

### Blob Storage Configuration

The application supports **two storage backends** for managing doctor profile files (photos, documents, certificates):

#### Local Storage (Default)

Files are stored on the local filesystem:

```properties
STORAGE_BACKEND=local
BLOB_STORAGE_PATH=./blob_storage
BLOB_BASE_URL=/api/v1/blobs
```

**Directory Structure:**
```
blob_storage/
├── {doctor_id}/
│   ├── profile_photo/
│   │   └── {blob_id}.jpg
│   ├── documents/
│   │   └── {blob_id}.pdf
│   └── achievements/
│       └── {blob_id}.png
```

**Best For:** Development, small deployments, single-server setups

---

#### AWS S3 Storage

Files are stored in AWS S3 bucket with optional signed URLs:

```properties
STORAGE_BACKEND=s3
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
AWS_S3_BUCKET=my-doctor-profiles
AWS_S3_PREFIX=doctors
AWS_S3_USE_SIGNED_URLS=false
AWS_S3_SIGNED_URL_EXPIRY=3600  # seconds
```

**S3 Key Structure:**
```
s3://my-doctor-profiles/
└── doctors/
    └── {doctor_id}/
        ├── profile_photo/
        │   └── {blob_id}.jpg
        └── documents/
            └── {blob_id}.pdf
```

**Best For:** Production, scalability, multi-region deployment, CDN integration

---

#### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `STORAGE_BACKEND` | `local` \| `s3` | `local` | Storage backend to use |
| `BLOB_STORAGE_PATH` | string | `./blob_storage` | Local storage directory path |
| `BLOB_BASE_URL` | string | `/api/v1/blobs` | Base URL for serving local blobs |
| `AWS_ACCESS_KEY_ID` | string | - | AWS access key (required for S3) |
| `AWS_SECRET_ACCESS_KEY` | string | - | AWS secret key (required for S3) |
| `AWS_REGION` | string | `us-east-1` | AWS region for S3 bucket |
| `AWS_S3_BUCKET` | string | - | S3 bucket name (required for S3) |
| `AWS_S3_PREFIX` | string | `doctors` | Prefix for all S3 object keys |
| `AWS_S3_USE_SIGNED_URLS` | boolean | `false` | Use signed URLs for private buckets |
| `AWS_S3_SIGNED_URL_EXPIRY` | integer | `3600` | Signed URL expiry time (seconds) |

---

#### Switching Between Backends

**No code changes required!** Simply update the `.env` file and restart:

```bash
# Switch from Local to S3
STORAGE_BACKEND=s3  # Change this line
# Add S3 credentials...

# Restart server
./venv/bin/uvicorn src.app.main:app --reload
```

The factory pattern automatically selects the correct storage implementation.

---

#### S3 Setup Guide

**1. Create S3 Bucket**
```bash
aws s3 mb s3://my-doctor-profiles --region us-east-1
```

**2. Configure Bucket Policy (Public Access)**
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "PublicReadGetObject",
    "Effect": "Allow",
    "Principal": "*",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::my-doctor-profiles/*"
  }]
}
```

**3. Create IAM User with Permissions**
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "s3:PutObject",
      "s3:GetObject",
      "s3:DeleteObject",
      "s3:HeadObject"
    ],
    "Resource": "arn:aws:s3:::my-doctor-profiles/*"
  }]
}
```

**4. Update Environment Variables**
```properties
STORAGE_BACKEND=s3
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_BUCKET=my-doctor-profiles
```

**5. For Private Buckets (Recommended for Production)**
```properties
AWS_S3_USE_SIGNED_URLS=true
AWS_S3_SIGNED_URL_EXPIRY=3600  # URLs expire after 1 hour
```

Keep bucket private and use signed URLs for secure access.

---

#### Storage Backend Comparison

| Feature | Local Storage | S3 Storage |
|---------|--------------|------------|
| **Setup** | ✅ Instant | ⚠️ Requires AWS account |
| **Cost** | ✅ Free (disk only) | 💰 Pay per GB + requests |
| **Scalability** | ⚠️ Limited by disk | ✅ Unlimited |
| **Availability** | ⚠️ Single point of failure | ✅ 99.99% SLA |
| **Backup** | ⚠️ Manual | ✅ Automatic versioning |
| **CDN Integration** | ❌ | ✅ CloudFront ready |
| **Multi-region** | ❌ | ✅ Built-in |
| **Performance** | ✅ Fast (local I/O) | ✅ Fast (global CDN) |

---


### AI Prompt Configuration

AI prompts are externalized in `config/prompts.yaml` for easy maintenance:

```yaml
# config/prompts.yaml
version: "2.0.0"
resume_extraction:
  system_prompt: |
    You are a medical document parser...
  response_schema: |
    { "personal_details": {...}, ... }
```

---

## 📡 API Reference

### Base URL
```
http://localhost:8000/api/v1
```

### Interactive Documentation
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### Authentication

All endpoints (except `/health`, `/live`, `/ready`) require a valid **Bearer JWT** in the `Authorization` header. Tokens are issued by the OTP verification flow.

```http
Authorization: Bearer <access_token>
```

### Core Endpoints

#### Health Probes (no auth required)
```http
GET /api/v1/health      # Comprehensive health check (DB + AI service)
GET /api/v1/ready       # Kubernetes readiness probe
GET /api/v1/live        # Kubernetes liveness probe
```

#### OTP Authentication
```http
POST /api/v1/auth/otp/request           # Send OTP to mobile number
POST /api/v1/auth/otp/verify           # Verify OTP + receive JWT (doctor flow)
POST /api/v1/auth/otp/resend           # Resend OTP
POST /api/v1/auth/admin/otp/verify     # Admin OTP verify (no auto-create)
POST /api/v1/auth/google/verify        # Google Sign-In verify
```

#### Doctor Management
```http
GET    /api/v1/doctors                          # List doctors (paginated, lightweight DoctorResponse)
GET    /api/v1/doctors?status=PENDING           # List by onboarding status (returns full DoctorWithFullInfoResponse)
GET    /api/v1/doctors/lookup                   # Full doctor profile by doctor_id / email / phone
GET    /api/v1/doctors/{id}                     # Get single doctor by ID
PUT    /api/v1/doctors/{id}                     # Update doctor profile (admin/operational only)
GET    /api/v1/doctors/bulk-upload/csv/template # Download template CSV with sample rows
POST   /api/v1/doctors/bulk-upload/csv/validate # Phase 1: validate CSV, return all row errors (no DB writes)
POST   /api/v1/doctors/bulk-upload/csv          # Phase 2: confirm upload, persist PENDING doctor records
```

#### Doctor Onboarding
```http
POST /api/v1/onboarding/extract-resume              # AI resume extraction (PDF/image → structured data)
GET  /api/v1/onboarding/email-template/{doctor_id}  # Pre-fill email template for admin popup (Admin/Operational)
POST /api/v1/onboarding/submit/{doctor_id}          # Submit own profile for admin review (any authenticated user)
POST /api/v1/onboarding/verify/{doctor_id}          # Admin: mark profile as verified + optional email
POST /api/v1/onboarding/reject/{doctor_id}          # Admin: reject profile with reason + optional email
```

#### Onboarding Admin (admin/operational role)
```http
POST   /api/v1/onboarding-admin/identities                  # Create doctor identity
GET    /api/v1/onboarding-admin/identities                  # Fetch identity by doctor_id or email
PUT    /api/v1/onboarding-admin/details/{doctor_id}         # Upsert doctor details (6-block questionnaire)
GET    /api/v1/onboarding-admin/details/{doctor_id}         # Fetch doctor details
POST   /api/v1/onboarding-admin/media/{doctor_id}           # Add media record (metadata only)
GET    /api/v1/onboarding-admin/media/{doctor_id}           # List media for a doctor
DELETE /api/v1/onboarding-admin/media/{media_id}            # Delete media record
POST   /api/v1/onboarding-admin/media/{doctor_id}/upload    # Upload file to blob storage + register
POST   /api/v1/onboarding-admin/status-history/{doctor_id}  # Log status change
GET    /api/v1/onboarding-admin/status-history/{doctor_id}  # Fetch status history
```

#### Voice Onboarding
```http
POST   /api/v1/voice/start                         # Start conversation session
POST   /api/v1/voice/chat                          # Send message, get AI response
GET    /api/v1/voice/session/{session_id}          # Get session status
POST   /api/v1/voice/session/{session_id}/finalize # Complete & persist session
DELETE /api/v1/voice/session/{session_id}          # Cancel session
```

#### Bulk Doctor CSV Upload (admin / operational role)

The bulk upload feature lets admin and operational users register up to **500 doctors at once** from a CSV file via a two-phase workflow.

##### Authentication & Authorization

All three endpoints require:
1. A valid **Bearer JWT** in the `Authorization` header (issued by `/auth/otp/verify` or `/auth/google/verify`)
2. The authenticated user's role must be **`admin`** or **`operational`** — `user` role is rejected with `403 Forbidden`

```http
Authorization: Bearer <access_token>
```

The auth chain for each request:
```
Bearer token
  └── require_authentication()   [JWT signature + expiry check — router-level]
        └── get_current_user()   [load User from DB, check is_active]
              └── require_admin_or_operational()  [role ∈ {admin, operational}]
```

##### Two-Phase Workflow

```
Step 1  POST /bulk-upload/csv/validate   ← upload CSV, get ALL row errors
           │
           ├── errors found  → fix CSV, repeat Step 1
           │
           └── valid=true, errors=[]
                    │
Step 2  POST /bulk-upload/csv           ← upload clean CSV, write to DB
           │
           ├── rows created with onboarding_status = PENDING
           └── audit entry added to doctor_status_history
```

##### Download Template

```http
GET /api/v1/doctors/bulk-upload/csv/template
Authorization: Bearer <token>
```

Returns the official CSV template pre-filled with two sample rows (Dr. Arjun Sharma — Cardiology; Dr. Priya Nair — Neurology). Fill in your data, remove the sample rows, then upload via the validate endpoint.

**Response:** `Content-Type: text/csv`, `Content-Disposition: attachment; filename="doctor_bulk_upload_template.csv"`

```bash
curl -O -J \
  -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/doctors/bulk-upload/csv/template
```

##### Phase 1 — Validate (no DB writes)

```http
POST /api/v1/doctors/bulk-upload/csv/validate
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

| Constraint | Value |
|------------|-------|
| Max rows | 500 |
| Encoding | UTF-8 (BOM stripped automatically) |
| Multi-value fields | Pipe-separated: `English\|Hindi\|Marathi` |
| Required columns | `first_name`, `last_name`, `phone` |
| Phone normalisation | Auto-converted to E.164 `+91XXXXXXXXXX` |

```bash
curl -X POST \
  -H "Authorization: Bearer <token>" \
  -F "file=@doctors.csv" \
  http://localhost:8000/api/v1/doctors/bulk-upload/csv/validate
```

**Response — valid file:**
```json
{
  "valid": true,
  "total_rows": 3,
  "error_count": 0,
  "errors": []
}
```

**Response — file with errors:**
```json
{
  "valid": false,
  "total_rows": 3,
  "error_count": 2,
  "errors": [
    { "row": 2, "field": "phone", "error": "'abc' is not a valid phone number (too short)." },
    { "row": 4, "field": "email", "error": "'notanemail' is not a valid email address." }
  ]
}
```

All errors across all rows are returned in one shot — fix everything, then re-validate.

**Validated fields per row:**

| Field | Validation |
|-------|-----------|
| `phone` | Required; digits only ≥ 10; normalised to `+91…` |
| `first_name` | Required; non-empty |
| `last_name` | Required; non-empty |
| `email` | Optional; must contain `@` and a dot in the domain when provided |
| `years_of_experience` | Optional; numeric 0–100 |
| `consultation_fee` | Optional; numeric ≥ 0 |
| `registration_year` | Optional; numeric 1900–2100 |
| `year_of_mbbs` | Optional; numeric 1900–2100 |
| `year_of_specialisation` | Optional; numeric 1900–2100 |
| `years_of_clinical_experience` | Optional; numeric 0–100 |
| `years_post_specialisation` | Optional; numeric 0–100 |

##### Phase 2 — Confirm Upload

```http
POST /api/v1/doctors/bulk-upload/csv
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

Runs the identical validation gate — returns `422` with the full error report if any row fails. Only a fully-clean file proceeds to database writes.

```bash
curl -X POST \
  -H "Authorization: Bearer <token>" \
  -F "file=@doctors_clean.csv" \
  http://localhost:8000/api/v1/doctors/bulk-upload/csv
```

**What happens for each row:**
- **New doctor** (no existing record with that phone): Creates a `doctors` row + `doctor_identity` row with `onboarding_status = PENDING` + an initial `doctor_status_history` audit entry.
- **Existing doctor** (phone already in DB): Updates profile fields in-place; onboarding status is **not** changed (they may already be `SUBMITTED` or `VERIFIED`).
- **DB-level error** (e.g. unique constraint race condition): The row is rolled back via savepoint; all other rows continue. The skipped row appears in `rows[].status = "skipped"`.

**Entire batch is atomic** — the outer transaction commits only after all rows have been processed. An unexpected system error rolls back everything.

**Response (all rows successful):**
```json
{
  "success": true,
  "message": "Processed 3 row(s): 2 created, 1 updated.",
  "total_rows": 3,
  "created": 2,
  "updated": 1,
  "skipped": 0,
  "rows": [
    { "row": 2, "status": "created", "doctor_id": 101, "phone": "+919988776655", "email": "arjun@example.com" },
    { "row": 3, "status": "created", "doctor_id": 102, "phone": "+919876543210", "email": "priya@example.com" },
    { "row": 4, "status": "updated", "doctor_id": 77,  "phone": "+918800001111", "email": null }
  ],
  "skipped_errors": []
}
```

**Response (one row skipped due to a DB-level race condition):**
```json
{
  "success": false,
  "message": "Processed 3 row(s): 2 created, 0 updated, 1 row(s) skipped due to errors.",
  "total_rows": 3,
  "created": 2,
  "updated": 0,
  "skipped": 1,
  "rows": [
    { "row": 2, "status": "created", "doctor_id": 101, "phone": "+919988776655", "email": "arjun@example.com" },
    { "row": 3, "status": "created", "doctor_id": 102, "phone": "+919876543210", "email": "priya@example.com" },
    { "row": 4, "status": "skipped",  "doctor_id": null, "phone": "9800001111",   "email": null }
  ],
  "skipped_errors": [
    { "row": 4, "field": null, "error": "Could not save row: UNIQUE constraint failed: doctors.email" }
  ]
}
```

**Error Responses:**

| HTTP | Scenario |
|------|----------|
| `400` | CSV encoding error, missing required columns, no data rows |
| `401` | Missing or invalid / expired JWT |
| `403` | User role is not `admin` or `operational` |
| `413` | More than 500 data rows |
| `422` | Row-level validation failures (full error list returned) |

##### CSV Template — Column Reference

The template contains 48 columns. Required columns are marked ✱.

| Column | Required | Notes |
|--------|----------|-------|
| `first_name` | ✱ | |
| `last_name` | ✱ | |
| `phone` | ✱ | Auto-normalised to E.164 |
| `email` | | If provided, creates `doctor_identity` row with PENDING status |
| `title` | | `Dr.`, `Prof.`, etc. |
| `gender` | | |
| `primary_specialization` | | |
| `medical_registration_number` | | |
| `medical_council` | | Full name of the issuing medical council |
| `registration_year` | | Numeric |
| `registration_authority` | | |
| `years_of_experience` | | Numeric 0–100 |
| `consultation_fee` | | Numeric ≥ 0 |
| `year_of_mbbs` | | Numeric 1900–2100 |
| `year_of_specialisation` | | Numeric 1900–2100 |
| `years_of_clinical_experience` | | Numeric 0–100 |
| `years_post_specialisation` | | Numeric 0–100 |
| `specialty` | | |
| `primary_practice_location` | | |
| `sub_specialties` | | Pipe-separated |
| `areas_of_expertise` | | Pipe-separated |
| `languages` | | Pipe-separated |
| `conditions_treated` | | Pipe-separated |
| `procedures_performed` | | Pipe-separated |
| `age_groups_treated` | | Pipe-separated |
| `awards_recognition` | | Pipe-separated |
| `memberships` | | Pipe-separated |
| `publications` | | Pipe-separated |
| `qualifications` | | Pipe-separated |
| `fellowships` | | Pipe-separated |
| `professional_memberships` | | Pipe-separated |
| `awards_academic_honours` | | Pipe-separated |
| `areas_of_clinical_interest` | | Pipe-separated |
| `practice_segments` | | |
| `conditions_commonly_treated` | | Pipe-separated |
| `conditions_known_for` | | Pipe-separated |
| `conditions_want_to_treat_more` | | Pipe-separated |
| `full_name` | | Display name |
| `professional_achievement` | | Free text |
| `personal_achievement` | | Free text |
| `professional_aspiration` | | Free text |
| `personal_aspiration` | | Free text |
| `what_patients_value_most` | | Free text |
| `approach_to_care` | | Free text |
| `availability_philosophy` | | Free text |
| `quality_time_interests_text` | | Free text |
| `professional_overview` | | Free text |
| `about_me` | | Free text |
| `professional_tagline` | | Free text |

---

#### Admin Verification & Email Notifications

When an admin verifies or rejects a doctor's profile, the backend can optionally
send an email notification to the doctor. The flow is:

1. **Admin opens the action popup** → frontend fetches the pre-filled template
2. **Admin edits** subject/body if desired
3. **Admin clicks Send (Verify / Reject)** → frontend calls the action endpoint with the final content

```
GET  /api/v1/onboarding/email-template/{doctor_id}?action=verified|rejected
POST /api/v1/onboarding/verify/{doctor_id}
POST /api/v1/onboarding/reject/{doctor_id}
```

All three endpoints require **Admin or Operational** role (Bearer token).

---

##### Step 1 — Fetch pre-filled template (for the popup)

```http
GET /api/v1/onboarding/email-template/{doctor_id}?action=verified
Authorization: Bearer <admin_token>
```

**Response `200 OK`:**
```json
{
  "success": true,
  "message": "Email template loaded successfully",
  "data": {
    "action": "verified",
    "doctor_id": 42,
    "doctor_email": "arjun.sharma@example.com",
    "subject": "🎉 Congratulations! Your LinQMD Profile Has Been Verified",
    "body_html": "<html>…pre-rendered HTML…</html>"
  }
}
```

The frontend displays `subject` and `body_html` in editable fields inside the popup.

---

##### Step 2 — Verify with optional email

```http
POST /api/v1/onboarding/verify/{doctor_id}
Authorization: Bearer <admin_token>
Content-Type: application/json
```

**Payload:**
```json
{
  "send_email": true,
  "email_subject": "Your LinQMD profile is verified!",
  "email_body": "<p>Dear Dr. Sharma…</p>"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `send_email` | `bool` | `false` | Set `true` to trigger email delivery |
| `email_subject` | `string \| null` | `null` | Admin-edited subject; uses template default if omitted |
| `email_body` | `string \| null` | `null` | Admin-edited HTML body; uses template default if omitted |

**Response `200 OK`:**
```json
{
  "success": true,
  "message": "Profile verified successfully",
  "data": {
    "doctor_id": 42,
    "previous_status": "submitted",
    "new_status": "verified",
    "verified_at": "2025-06-01T10:30:00+00:00",
    "email_sent": true
  }
}
```

> **Non-blocking email**: If SMTP delivery fails, the verification is **not rolled back**.
> The response will include `"email_sent": false` and an `"email_error"` field with the reason.
> The status change is always committed atomically.

---

##### Step 3 — Reject with optional email

```http
POST /api/v1/onboarding/reject/{doctor_id}
Authorization: Bearer <admin_token>
Content-Type: application/json
```

**Payload:**
```json
{
  "reason": "Registration certificate image is blurry — please re-upload.",
  "send_email": true,
  "email_subject": null,
  "email_body": null
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `reason` | `string \| null` | `null` | Rejection reason stored in audit log and injected into email template |
| `send_email` | `bool` | `false` | Set `true` to trigger email delivery |
| `email_subject` | `string \| null` | `null` | Admin-edited subject; uses template default if omitted |
| `email_body` | `string \| null` | `null` | Admin-edited HTML body; uses template default if omitted |

**Response `200 OK`:**
```json
{
  "success": true,
  "message": "Profile rejected successfully",
  "data": {
    "doctor_id": 42,
    "previous_status": "submitted",
    "new_status": "rejected",
    "reason": "Registration certificate image is blurry — please re-upload.",
    "email_sent": true
  }
}
```

---

##### Email Template Configuration

Templates live in **`config/email_templates.yaml`** and are loaded from disk at runtime.
To customise email copy, edit that file — no code change or redeploy required (restart the server to pick up changes).

**Available placeholder variables:**

| Placeholder | Description |
|-------------|-------------|
| `{doctor_name}` | Full name with title (e.g. `Dr. Arjun Sharma`) |
| `{first_name}` | Doctor's first name |
| `{medical_registration_number}` | MRN on file |
| `{medical_council}` | Issuing medical council |
| `{specialization}` | Primary specialisation |
| `{reason}` | Rejection reason (only relevant in `rejected` template) |
| `{platform_name}` | Taken from `EMAIL_FROM_NAME` env variable |
| `{support_email}` | Taken from `EMAIL_FROM_ADDRESS` env variable |

---

##### Frontend Integration Checklist

> **What the frontend must implement:**

- [ ] **GET `/email-template/{doctor_id}?action=verified`** when the admin opens the Verify popup — populate the Subject and Body fields with the response.
- [ ] **GET `/email-template/{doctor_id}?action=rejected`** when the admin opens the Reject popup — same.
- [ ] Render the popup with:
  - A **read-only** "To:" field showing `doctor_email` from the response.
  - An **editable** "Subject" text input pre-filled with `subject`.
  - An **editable** rich-text / textarea pre-filled with `body_html` (render as HTML preview or raw source, depending on your editor).
  - A **"Send email"** toggle/checkbox (default: on).
- [ ] On **Verify / Reject** button click, POST to the respective endpoint with:
  - `send_email: true` (if toggle is on)
  - `email_subject`: current value of the subject field (pass `null` if unchanged to use template default)
  - `email_body`: current value of the body field (pass `null` if unchanged to use template default)
- [ ] Show a **success toast** if `email_sent === true`.
- [ ] Show a **warning toast** if `email_sent === false && email_error` is present (e.g. "Profile verified but email could not be sent: \<error\>").
- [ ] The **Subject** and **Body** fields are always optional — if the admin closes the popup without editing, pass `null` for both to use template defaults.

---

#### Dropdown Options (Speciality & Other Fields)

The platform manages all dropdown option lists through a **3-status approval workflow**:

| Status | Visible in public dropdowns? | Created by |
|--------|------------------------------|------------|
| `approved` | ✅ Yes | Admin direct-create **or** approved user submission |
| `pending` | ❌ No — hidden until reviewed | Doctor / user `POST /dropdowns/submit` |
| `rejected` | ❌ Never | Admin reject action |

---

##### Supported dropdown fields

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

##### Public endpoints (no auth)

```http
GET /api/v1/dropdowns
GET /api/v1/dropdowns/{field_name}
```

**`GET /api/v1/dropdowns`** — all fields at once:
```json
{
  "success": true,
  "message": "Dropdown options loaded successfully",
  "data": {
    "supported_fields": ["age_groups_treated", "fellowships", "..."],
    "fields": {
      "specialty": {
        "field_name": "specialty",
        "description": "Medical specialisation",
        "options": [
          { "id": 1, "value": "Cardiology", "label": "Cardiology", "display_order": 0 },
          { "id": 2, "value": "Neurology",  "label": "Neurology",  "display_order": 0 }
        ]
      }
    }
  }
}
```

**`GET /api/v1/dropdowns/specialty`** — single field.

---

##### User submission (authenticated — any role)

```http
POST /api/v1/dropdowns/submit
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "field_name": "specialty",
  "value": "Sports Medicine",
  "label": "Sports Medicine"
}
```

**Response `202 Accepted`:**
```json
{
  "success": true,
  "message": "'Sports Medicine' has been submitted for 'specialty' and is pending admin review.",
  "data": {
    "id": 183,
    "field_name": "specialty",
    "value": "Sports Medicine",
    "label": "Sports Medicine",
    "status": "pending",
    "message": "..."
  }
}
```

> The value is **not** visible in public dropdowns until approved.
> Submitting an already-existing value returns the existing record without creating a duplicate.

---

##### Admin endpoints (Admin / Operational role)

```http
GET    /api/v1/admin/dropdowns                        # List all (filter: field, status, search)
GET    /api/v1/admin/dropdowns/pending                # Pending-only (badge view)
GET    /api/v1/admin/dropdowns/fields                 # List supported field names
GET    /api/v1/admin/dropdowns/{option_id}            # Get single option
POST   /api/v1/admin/dropdowns                        # Create option (approved immediately)
PATCH  /api/v1/admin/dropdowns/{option_id}            # Update label / display_order
DELETE /api/v1/admin/dropdowns/{option_id}            # Delete (system rows protected)
POST   /api/v1/admin/dropdowns/{option_id}/approve    # Approve a PENDING option
POST   /api/v1/admin/dropdowns/{option_id}/reject     # Reject a PENDING option
POST   /api/v1/admin/dropdowns/bulk-approve           # Approve up to 200 at once
POST   /api/v1/admin/dropdowns/bulk-reject            # Reject up to 200 at once
```

**Approve a pending submission:**
```http
POST /api/v1/admin/dropdowns/183/approve
Authorization: Bearer <admin_token>
Content-Type: application/json

{ "review_notes": "Verified — valid specialty." }
```

**Bulk-approve:**
```http
POST /api/v1/admin/dropdowns/bulk-approve
Authorization: Bearer <admin_token>
Content-Type: application/json

{ "option_ids": [183, 184, 185], "review_notes": "Batch approved after review." }
```

**List pending (for admin badge / notification count):**
```http
GET /api/v1/admin/dropdowns/pending
Authorization: Bearer <admin_token>
```
```json
{
  "data": {
    "items": [...],
    "total": 3,
    "pending_count": 3
  }
}
```

---

##### Frontend Integration Checklist — Dropdowns

> **What the frontend must implement:**

**Doctor / user registration form:**
- [ ] On page load, call `GET /api/v1/dropdowns` once and cache the full `fields` map.
- [ ] Populate each dropdown field from `fields[field_name].options`.
- [ ] For each dropdown, add an **"+ Add new value"** option/button.
- [ ] When "Add new value" is clicked, show a small text input for the new value.
- [ ] On submit of the new value, call `POST /api/v1/dropdowns/submit` with `field_name` + `value`.
- [ ] Show the user a confirmation: *"Your value has been submitted and is pending review. It will appear in the list once approved."*
- [ ] Do **not** pre-select the submitted value in the current session's dropdown (it is `pending`, not yet approved).

**Admin portal — Dropdown Management page:**
- [ ] Show a **badge** / counter for pending submissions: `GET /api/v1/admin/dropdowns/pending` → `data.pending_count`.
- [ ] Render a table of all dropdown options with columns: Field, Value, Status, Submitted by, Submitted at.
- [ ] Support filtering by `field_name`, `status`, and `search`.
- [ ] Per row: **Approve** button → `POST /admin/dropdowns/{id}/approve`.
- [ ] Per row: **Reject** button → `POST /admin/dropdowns/{id}/reject` with optional `review_notes`.
- [ ] Support **multi-select + bulk approve / bulk reject** → `POST /admin/dropdowns/bulk-approve` or `bulk-reject`.
- [ ] Provide a **"+ Add option"** form → `POST /api/v1/admin/dropdowns` (creates as `approved` immediately).
- [ ] Allow editing display label and sort order via `PATCH /admin/dropdowns/{id}`.
- [ ] Allow deletion of non-system rows via `DELETE /admin/dropdowns/{id}`.
- [ ] System rows (`is_system: true`) should show a 🔒 lock icon and disable Delete.

---

#### Admin User Management (admin role only)
```http
GET    /api/v1/admin/users              # List users
GET    /api/v1/admin/users/{user_id}    # Get user
PATCH  /api/v1/admin/users/{user_id}    # Update role / active / doctor_id
DELETE /api/v1/admin/users/{user_id}    # Delete user
```

### Response Format

**Success:**
```json
{
  "message": "Operation successful",
  "data": {}
}
```

**Paginated:**
```json
{
  "message": "Items retrieved",
  "data": [],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_items": 100,
    "total_pages": 5,
    "has_next": true,
    "has_previous": false
  }
}
```

**Error:**
```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "details": {}
  }
}
```

### Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `UNAUTHORIZED` | 401 | Missing or invalid token |
| `INVALID_TOKEN` | 401 | Token is invalid |
| `OTP_EXPIRED` | 401 | OTP has expired |
| `INVALID_OTP` | 401 | OTP is incorrect |
| `USER_NOT_FOUND` | 401 | User not in users table |
| `USER_INACTIVE` | 403 | User account deactivated |
| `ADMIN_REQUIRED` | 403 | Admin role required |
| `INSUFFICIENT_PERMISSIONS` | 403 | Role lacks permissions |
| `DOCTOR_NOT_FOUND` | 404 | Doctor record not found |
| `VALIDATION_ERROR` | 422 | Request validation failed |
| `EXTRACTION_ERROR` | 422 | AI extraction failed |

### Rate Limits

| Endpoint Type | Limit |
|--------------|-------|
| OTP Request | 3 per minute per phone |
| OTP Verify | 5 attempts per OTP |
| Resume Extraction | 10 per minute |
| Voice Chat | 60 per minute per session |
| Admin APIs | 100 per minute |

### Example Usage

#### Extract Data from Resume
```bash
curl -X POST http://localhost:8000/api/v1/onboarding/extract-resume \
  -F "file=@doctor_resume.pdf"
```

#### Create Doctor Record
```bash
curl -X POST http://localhost:8000/api/v1/doctors \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Sarah",
    "last_name": "Johnson",
    "email": "sarah.johnson@hospital.com",
    "primary_specialization": "Cardiology",
    "medical_registration_number": "MED123456"
  }'
```

#### Start Voice Session
```bash
curl -X POST http://localhost:8000/api/v1/voice/start \
  -H "Content-Type: application/json" \
  -d '{"language": "en"}'
```

---

## 🗄️ Database Schema

The application uses a **single PostgreSQL database** managed exclusively by **Alembic**. There is no dual-DB architecture. SQLite is only used in the test suite (in-memory, via `aiosqlite`).

### Tables

| Table | Purpose |
|-------|---------|
| `doctors` | Core doctor profile — personal, professional, JSON arrays for lists |
| `users` | RBAC user accounts linked to doctors (`admin`, `operational`, `user`) |
| `doctor_identity` | Onboarding identity + status (`pending`, `submitted`, `verified`, `rejected`) |
| `doctor_details` | Full professional questionnaire (6 blocks, 50+ fields) |
| `doctor_media` | Uploaded file references (profile photo, degree certificates, etc.) |
| `doctor_status_history` | Immutable audit log of every status transition |
| `dropdown_options` | Curated dropdown values for onboarding form fields (~205 system values across 15 fields seeded by the initial migration; user submissions start as `pending` until approved) |

### Key Design Decisions

- **Media stored outside DB**: `doctor_media` stores file URIs (local path or S3 key); binary blobs are never stored in the DB
- **Status tracked twice**: `doctors.onboarding_status` (fast lookup) and `doctor_identity.onboarding_status` (onboarding pipeline) — kept in sync by the status endpoints
- **Audit trail**: Every `verify` / `reject` action appends an immutable row to `doctor_status_history` via `flush()` so it commits atomically with the status update
- **Race-safe IDs**: `doctor_identity.doctor_id` uses the `doctor_id_seq` PostgreSQL sequence instead of `MAX+1`

### Migrations

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
| `001` | Complete schema: 7 tables, all indexes, `doctor_id_seq`, admin user seed, ~205 dropdown seed values across 15 fields |

### Indexes
- `doctors.email` — unique
- `doctors.medical_registration_number` — B-tree (fast lookup; not unique at DB level)
- `doctor_identity.doctor_id` — unique
- `doctor_identity.email` — unique
- `doctor_identity.onboarding_status` — B-tree (fast filtered listing)
- `users.phone` — unique
- `dropdown_options.field_name` — B-tree
- `dropdown_options.(field_name, value)` — unique constraint

> **`medical_council`** is stored as a plain `VARCHAR(200)` nullable column on both `doctors` and `doctor_details` tables.  It travels alongside `medical_registration_number` and is populated via API, resume extraction, voice onboarding, and CSV bulk upload.

### Detailed Table Schemas

#### `doctor_identity`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `VARCHAR(36)` | PK, UUID v4 | Unique identifier |
| `doctor_id` | `BIGINT` | UNIQUE, NOT NULL | Numeric doctor ID (from `doctor_id_seq`) |
| `title` | `ENUM` | NULLABLE | `'dr'`, `'prof'`, `'prof.dr'` |
| `first_name` | `VARCHAR(100)` | NOT NULL | First name |
| `last_name` | `VARCHAR(100)` | NOT NULL | Last name |
| `email` | `VARCHAR(255)` | UNIQUE, NOT NULL | Email address |
| `phone_number` | `VARCHAR(20)` | NOT NULL | Contact phone |
| `onboarding_status` | `ENUM` | NOT NULL, default `'pending'` | `pending` \| `submitted` \| `verified` \| `rejected` |
| `status_updated_at` | `TIMESTAMP WITH TZ` | NULLABLE | Last status change time |
| `status_updated_by` | `VARCHAR(36)` | NULLABLE | Admin who updated status |
| `rejection_reason` | `TEXT` | NULLABLE | Reason if rejected |
| `verified_at` | `TIMESTAMP WITH TZ` | NULLABLE | Verification completion time |
| `is_active` | `BOOLEAN` | NOT NULL, default `TRUE` | Soft delete flag |
| `registered_at` | `TIMESTAMP WITH TZ` | NOT NULL, default UTC NOW | Registration time |
| `created_at` | `TIMESTAMP WITH TZ` | NOT NULL | Row creation time |
| `updated_at` | `TIMESTAMP WITH TZ` | NOT NULL | Row update time |
| `deleted_at` | `TIMESTAMP WITH TZ` | NULLABLE | Soft delete time |

#### `doctor_details`
| Column | Type | Description |
|--------|------|-------------|
| `detail_id` | `VARCHAR(36)` PK | UUID identifier |
| `doctor_id` | `BIGINT` FK | References `doctor_identity.doctor_id` (CASCADE DELETE) |
| **Block 1 – Professional Identity** | | |
| `full_name`, `specialty`, `primary_practice_location` | `VARCHAR` | Identity fields |
| `centres_of_practice`, `years_of_clinical_experience`, `years_post_specialisation` | `JSON` / `INTEGER` | Practice details |
| **Block 2 – Credentials & Trust Markers** | | |
| `year_of_mbbs`, `year_of_specialisation` | `INTEGER` | Education years |
| `fellowships`, `qualifications`, `professional_memberships`, `awards_academic_honours` | `JSON[]` | Credentials arrays |
| **Block 3 – Clinical Focus** | | |
| `areas_of_clinical_interest`, `conditions_commonly_treated`, `conditions_known_for`, `conditions_want_to_treat_more` | `JSON[]` | Clinical focus |
| **Block 4 – The Human Side** | | |
| `training_experience`, `motivation_in_practice`, `unwinding_after_work`, `recognition_identity`, `quality_time_interests` | `JSON[]` | Personal side |
| `professional_achievement`, `personal_achievement`, `professional_aspiration`, `personal_aspiration` | `TEXT` | Narrative fields |
| **Block 5 – Patient Value** | | |
| `what_patients_value_most`, `approach_to_care`, `availability_philosophy` | `TEXT` | Patient relationship |
| **Block 6 – Content Seeds** | | |
| `content_seeds` | `JSON[]` | Content seed objects |
| **Legacy / compatibility fields** | | |
| `speciality`, `registration_number`, `consultation_fee`, `professional_overview`, `about_me`, etc. | mixed | Backward compat fields |

#### `doctor_media`
| Column | Type | Description |
|--------|------|-------------|
| `media_id` | `VARCHAR(36)` PK UUID | Unique identifier |
| `doctor_id` | `BIGINT` FK | References `doctor_identity.doctor_id` (CASCADE DELETE) |
| `media_type` | `VARCHAR(50)` | `'image'`, `'document'`, `'video'` |
| `media_category` | `VARCHAR(50)` | `'profile_photo'`, `'certificate'`, etc. |
| `file_uri` | `TEXT` NOT NULL | Local path or S3 URL |
| `file_name` | `VARCHAR(255)` | Original filename |
| `file_size` | `BIGINT` | Bytes |
| `mime_type` | `VARCHAR(100)` | e.g. `'image/jpeg'` |
| `is_primary` | `BOOLEAN` | Primary file for this category |
| `upload_date` | `TIMESTAMP WITH TZ` | Upload timestamp |

#### `doctor_status_history`
| Column | Type | Description |
|--------|------|-------------|
| `history_id` | `VARCHAR(36)` PK UUID | Unique identifier |
| `doctor_id` | `BIGINT` FK | References `doctor_identity.doctor_id` (CASCADE DELETE) |
| `previous_status` | `ENUM` NULLABLE | Status before change |
| `new_status` | `ENUM` NOT NULL | Status after change |
| `changed_by` | `VARCHAR(36)` | Admin user ID |
| `rejection_reason` | `TEXT` | Reason if rejected |
| `notes` | `TEXT` | Additional notes |
| `changed_at` | `TIMESTAMP WITH TZ` | When change occurred |

#### `users`
| Column | Type | Description |
|--------|------|-------------|
| `id` | `SERIAL` PK | Auto-increment |
| `phone` | `VARCHAR(20)` UNIQUE NOT NULL | `+91XXXXXXXXXX` format |
| `email` | `VARCHAR(255)` UNIQUE NULLABLE | Email address |
| `role` | `VARCHAR(20)` NOT NULL, default `'user'` | `admin` \| `operational` \| `user` |
| `is_active` | `BOOLEAN` NOT NULL, default `TRUE` | Soft delete |
| `doctor_id` | `INTEGER` FK NULLABLE | Links to `doctors.id` (SET NULL on delete) |
| `created_at` | `TIMESTAMP WITH TZ` NOT NULL | Creation time |
| `updated_at` | `TIMESTAMP WITH TZ` NULLABLE | Update time |
| `last_login_at` | `TIMESTAMP WITH TZ` NULLABLE | Last login |

#### `dropdown_options`
| Column | Type | Description |
|--------|------|-------------|
| `id` | `INTEGER` PK (autoincrement) | Unique identifier |
| `field_name` | `VARCHAR(100)` NOT NULL, indexed | e.g. `'specialty'`, `'qualifications'` |
| `value` | `VARCHAR(255)` NOT NULL | Option value (unique per `field_name`) |
| `label` | `VARCHAR(255)` NULLABLE | Human-readable display label (defaults to `value`) |
| `status` | `ENUM` NOT NULL, default `'pending'` | `approved` \| `pending` \| `rejected` |
| `is_system` | `BOOLEAN` NOT NULL, default `FALSE` | System-seeded rows — cannot be deleted |
| `display_order` | `INTEGER` NOT NULL, default `0` | Sort order for display |
| `submitted_by` | `VARCHAR(36)` NULLABLE | User ID who submitted (for user-submitted rows) |
| `submitted_by_email` | `VARCHAR(255)` NULLABLE | Email of the submitter |
| `reviewed_by` | `VARCHAR(36)` NULLABLE | Admin ID who approved/rejected |
| `reviewed_by_email` | `VARCHAR(255)` NULLABLE | Email of the reviewer |
| `reviewed_at` | `TIMESTAMP WITH TZ` NULLABLE | When the row was reviewed |
| `review_notes` | `TEXT` NULLABLE | Admin notes on approval/rejection |
| `created_at` | `TIMESTAMP WITH TZ` NOT NULL | Row creation time |
| `updated_at` | `TIMESTAMP WITH TZ` NOT NULL | Row update time |

> **Unique constraint:** `(field_name, value)` — submitting the same value twice returns the existing record.

---

## 🎤 Voice Onboarding Flow

The voice onboarding system implements a **state machine** pattern for natural conversations:

### Session States
- `active`: Collecting information
- `completed`: All fields collected
- `expired`: Session timed out

### Field Collection Order
1. `full_name` - Professional title + name
2. `primary_specialization` - Medical specialty
3. `years_of_experience` - Practice duration
4. `medical_registration_number` - License number
5. `email` - Contact email
6. `phone_number` - Phone contact
7. `languages` - Spoken languages

### Conversation Flow
```
User: "Hi, I'm Dr. Sarah Johnson, a cardiologist"

AI: "Nice to meet you, Dr. Johnson! I've noted your specialization as Cardiology.
     What's your medical registration number?"

User: "It's MED123456"

AI: "Your registration number is MED123456. Can you confirm that's correct?"

[... continues until all fields collected ...]

AI: "Perfect! I've collected all the information. Let me summarize..."
```

### Session Management
- **In-memory storage** with automatic cleanup
- **30-minute expiry** with periodic background cleanup
- **Field confidence scoring** for data quality
- **Graceful error recovery** for unclear responses

---

## 🛠 Development Guide

### Code Quality

```bash
# Run all checks
pre-commit run --all-files

# Format code
ruff format .

# Lint code
ruff check . --fix

# Type check
mypy src/

# Run tests
pytest
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Add new field"

# Apply migrations
alembic upgrade head

# Downgrade
alembic downgrade -1
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test
pytest tests/test_doctors.py::test_create_doctor
```

### API Development

```bash
# Auto-reload during development
uvicorn src.app.main:app --reload

# With custom host/port
uvicorn src.app.main:app --host 0.0.0.0 --port 8000

# Production server
uvicorn src.app.main:app --workers 4 --host 0.0.0.0 --port 8000
```

---

## 🧪 Testing

### Test Structure
```
tests/
├── conftest.py                       # Async SQLite engine, db_session, client fixtures
├── unit/
│   ├── test_auth_schemas.py          # _normalise_indian_mobile, OTP schemas (22 tests)
│   ├── test_jwt_helpers.py           # encode/decode/expiry/tamper (15 tests)
│   └── test_doctor_utils.py          # synthesise_identity() (15 tests)
├── integration/
│   ├── test_doctor_repository.py     # DoctorRepository CRUD (27 tests)
│   ├── test_onboarding_repository.py # OnboardingRepository (26 tests)
│   ├── test_user_repository.py       # UserRepository + update_fields atomicity (30 tests)
│   └── test_otp_endpoints.py         # OTP HTTP endpoints, mocked OTP service (17 tests)
├── api/                              # HTTP endpoint tests (existing)
├── core/                             # Core module tests (existing)
└── services/                         # Service-layer tests (existing)
```

Tests use **in-memory SQLite** (`aiosqlite`) — no real DB or external services needed.

### Running Tests

```bash
# All tests
pytest

# Unit tests only (fastest, no DB required)
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# With coverage report
pytest --cov=src --cov-report=term-missing

# Specific test file
pytest tests/integration/test_user_repository.py -v
```

### Test Categories
- **Unit Tests** (`tests/unit/`): Pure in-process — no DB, no HTTP, no services
- **Integration Tests** (`tests/integration/`): In-memory SQLite DB; HTTP endpoints mocked at service layer
- **API Tests** (`tests/api/`): Full HTTP endpoint tests with `AsyncClient`

---

## ⚙️ CI/CD Pipeline

A GitHub Actions workflow is included at **`.github/workflows/ci.yml`** and runs automatically on every push and pull request to `main`, `master`, or `develop`.

### Jobs

| Job | What it does |
|-----|-------------|
| **lint** | `ruff check` + `ruff format --check` — fails fast on style issues |
| **typecheck** | `mypy src/` — static type checking |
| **test** | `pytest --cov=src --cov-fail-under=60` — full test suite with Redis service container |
| **docker-build** | `docker buildx build` — verifies the image builds successfully (no push) |
| **security** | `pip-audit` — dependency vulnerability scan (non-blocking / informational) |

### Environment in CI

The test job injects all required env vars (`DATABASE_URL`, `SECRET_KEY`, `GOOGLE_API_KEY`, Firebase vars, SMS vars, etc.) from repository secrets / CI defaults. A Redis service container (`redis:7-alpine`) is spun up so OTP tests run against a real in-memory store.

### Setting up secrets

For the `test` job to pass fully, add these to your repo's **Settings → Secrets and variables → Actions**:

| Secret | Description |
|--------|-------------|
| `GOOGLE_API_KEY` | Gemini API key (can be a test/CI key) |
| `FIREBASE_PROJECT_ID` | Firebase project ID |
| `FIREBASE_WEB_API_KEY` | Firebase web API key |
| `SMS_USER_ID` | SMS gateway user ID |
| `SMS_USER_PASS` | SMS gateway password |
| `SMS_GSM_ID` | SMS sender ID |
| `SMS_PE_ID` | SMS PE ID |
| `SMS_TEMPLATE_ID` | SMS template ID |

> Tests that mock external services (Gemini, Firebase, SMS) will pass with placeholder values.
> Only integration tests that make live API calls require real credentials.

---

## 🚢 Deployment

### Pre-Deployment Checklist

Before going to production, verify the following:

**Environment:**
- [ ] `APP_ENV=production`, `DEBUG=False`
- [ ] `SECRET_KEY` is a strong random key (64+ chars): `python -c "import secrets; print(secrets.token_urlsafe(64))"`
- [ ] `DATABASE_URL` points to production PostgreSQL (not localhost)
- [ ] `GOOGLE_API_KEY`, `SMS_USER_ID`, `SMS_USER_PASS` are set

**Database:**
- [ ] PostgreSQL 16+ is running and accessible
- [ ] `DATABASE_POOL_SIZE` and `DATABASE_MAX_OVERFLOW` are tuned
- [ ] All migrations applied: `alembic upgrade head`
- [ ] Database backups are configured
- [ ] SSL/TLS enabled for DB connections

**Security:**
- [ ] CORS origins are restricted (not `*`)
- [ ] HTTPS is enforced at load balancer
- [ ] API docs disabled in production (`docs_url=None`, `redoc_url=None`, `openapi_url=None`)
- [ ] Redis running for OTP store (`REDIS_ENABLED=True`)

**Monitoring:**
- [ ] Health endpoint accessible: `GET /api/v1/health`
- [ ] Readiness probe: `GET /api/v1/ready`
- [ ] Liveness probe: `GET /api/v1/live`
- [ ] Structured JSON logging configured

### Production Server Start

```bash
# Gunicorn with uvicorn workers (recommended for production)
gunicorn src.app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120

# Worker sizing: workers = (2 * CPU cores) + 1
# Memory: 512MB–1GB per worker (1GB recommended for AI operations)
```

### Docker Production Build

```bash
# Build production image
docker build -t doctor-onboarding:latest .

# Run standalone (entrypoint.sh runs migrations automatically before starting)
docker run -p 8000:8000 \
  -e APP_ENV=production \
  -e DATABASE_URL=postgresql+asyncpg://user:pass@db-host:5432/doctor_onboarding \
  -e REDIS_URL=redis://redis-host:6379/0 \
  -e SECRET_KEY=your-64-char-random-key \
  -e GOOGLE_API_KEY=your_key \
  -e SMS_USER_ID=your_sms_user \
  -e SMS_USER_PASS=your_sms_pass \
  doctor-onboarding:latest

# Verify it started correctly
curl http://localhost:8000/api/v1/live    # → {"status": "alive"}
curl http://localhost:8000/api/v1/ready   # → {"status": "ready"}
```

### Docker Compose (Full Stack)

```bash
# Start the full stack (API + PostgreSQL + Redis)
# Migrations run automatically before the app starts (via entrypoint.sh)
docker compose up -d

# With a production-specific env file
docker compose --env-file .env.prod up -d

# View logs
docker compose logs -f api

# Stop (keep volumes)
docker compose down

# Stop + wipe all data (fresh start)
docker compose down -v
```

> **Note:** There is a single `docker-compose.yml` for all environments.
> Override `APP_ENV`, `DATABASE_URL`, `DEBUG`, and other variables via `.env` or `--env-file` for production.

```bash
# Quick check that the stack is healthy
curl http://localhost:8000/api/v1/live    # → {"status": "alive"}
curl http://localhost:8000/api/v1/ready   # → {"status": "ready"}
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: doctor-onboarding
spec:
  replicas: 3
  selector:
    matchLabels:
      app: doctor-onboarding
  template:
    spec:
      containers:
      - name: api
        image: doctor-onboarding:latest
        ports:
        - containerPort: 8000
        env:
        - name: GOOGLE_API_KEY
          valueFrom:
            secretKeyRef:
              name: gemini-secrets
              key: api-key
        livenessProbe:
          httpGet:
            path: /api/v1/live
            port: 8000
        readinessProbe:
          httpGet:
            path: /api/v1/ready
            port: 8000
```

### Rollback Procedure

```bash
# Roll back database one migration
alembic downgrade -1

# Roll back to specific revision
alembic downgrade <revision_id>

# Application rollback (Docker)
docker pull doctor-onboarding:previous-version
docker stop doctor-onboarding
docker run -d --name doctor-onboarding ... doctor-onboarding:previous-version
```

---

## 🔧 Troubleshooting

### Common Issues

#### Docker Issues

| Problem | Solution |
|---------|----------|
| **`docker compose up` fails — port 5432 already in use** | A local PostgreSQL is running. Stop it (`brew services stop postgresql@15`) or change the db port in `docker-compose.yml` to `"5433:5432"` |
| **`docker compose up` fails — port 6379 already in use** | A local Redis is running. Stop it (`brew services stop redis`) or change the redis port to `"6380:6379"` |
| **API container exits immediately after starting** | Check logs: `docker compose logs api`. Usually means `DATABASE_URL` is wrong or PostgreSQL isn't healthy yet |
| **`PGADMIN_PASSWORD must be set` error** | Set `PGADMIN_PASSWORD=change-me` in your `.env` file (only required when using `--profile tools`) |
| **Migrations failed on startup** | Check `docker compose logs api` for the alembic error. Fix and run `docker compose up --build` to rebuild |
| **`/api/v1/ready` returns error after `docker compose up`** | Wait a few more seconds — the DB health check might still be initialising. Run `docker compose ps` to check service states |
| **Swagger UI blank page at `/docs`** | Make sure `APP_ENV` is NOT set to `production` — the CSP middleware relaxes for docs only in non-production environments |
| **Want a fresh database** | `docker compose down -v && docker compose up --build` — this deletes all volumes and starts clean |

#### API Key Issues
```bash
# Check API key configuration
curl http://localhost:8000/api/v1/health

# Verify Gemini API access
python -c "import google.genai as genai; genai.configure(api_key='your_key')"
```

#### Database Connection
```bash
# Test database connectivity
alembic current

# Reset database
alembic downgrade base
alembic upgrade head
```

#### Memory Issues
```bash
# Monitor memory usage
docker stats

# Check voice session cleanup
curl http://localhost:8000/api/v1/health
```

### Debug Mode

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
export DEBUG=true

# Check application logs
docker compose logs api
```

### Performance Tuning

```bash
# Database connection pooling
export DATABASE_POOL_SIZE=10
export DATABASE_MAX_OVERFLOW=20

# Worker processes
uvicorn src.app.main:app --workers 4

# Memory limits
docker run --memory=1g --memory-swap=2g
```

---

## 🤝 Contributing

### Development Workflow

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/new-feature`
3. **Make** your changes with tests
4. **Run** quality checks: `pre-commit run --all-files`
5. **Submit** a pull request

### Code Standards

- **Type Hints**: 100% coverage required
- **Docstrings**: Google style for all public functions
- **Tests**: Minimum 80% coverage
- **Linting**: Ruff compliant
- **Formatting**: Black compatible

### Commit Messages

```
feat: add voice session timeout handling
fix: resolve database connection leak
docs: update API reference for v2 endpoints
test: add integration tests for doctor CRUD
```

---

## 📄 License

**MIT License** — add a `LICENSE` file to the repository root before open-sourcing.

## 🙏 Acknowledgments

- **FastAPI** team for the excellent framework
- **Google AI** for Gemini API access
- **SQLAlchemy** for robust ORM capabilities
- **Pydantic** for type-safe data validation

---

**Built with ❤️ for healthcare professionals worldwide**
