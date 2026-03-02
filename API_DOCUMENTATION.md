# Doctor Onboarding API - Complete Documentation

**Base URL:** `http://127.0.0.1:6555/api/v1`

**Total Endpoints:** 58

---

## Table of Contents

1. [Authentication (5 endpoints)](#1-authentication)
2. [Health Check (3 endpoints)](#2-health-check)
3. [Doctors (7 endpoints)](#3-doctors)
4. [Dropdowns (3 endpoints)](#4-dropdowns)
5. [Onboarding (5 endpoints)](#5-onboarding)
6. [Voice Onboarding (5 endpoints)](#6-voice-onboarding)
7. [Onboarding Admin (10 endpoints)](#7-onboarding-admin)
8. [Admin Users (9 endpoints)](#8-admin-users)
9. [Admin Dropdowns (11 endpoints)](#9-admin-dropdowns)

---

## 1. AUTHENTICATION

### 1.1 Request OTP
**POST** `/auth/otp/request`

Send OTP to mobile number for authentication. No auth required.

**Request Body:**
```json
{
  "mobile_number": "9443453525"
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/auth/otp/request' \
  -H 'Content-Type: application/json' \
  -d '{"mobile_number": "9443453525"}'
```

**Response (200):**
```json
{
  "success": true,
  "message": "OTP sent successfully",
  "mobile_number": "94****3525",
  "expires_in_seconds": 300
}
```

---

### 1.2 Verify OTP
**POST** `/auth/otp/verify`

Verify OTP and receive a JWT access token. Creates a new doctor record if the mobile number is not registered.

**Request Body:**
```json
{
  "mobile_number": "9443453525",
  "otp": "123456"
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/auth/otp/verify' \
  -H 'Content-Type: application/json' \
  -d '{"mobile_number": "9443453525", "otp": "123456"}'
```

**Response (200):**
```json
{
  "success": true,
  "message": "OTP verified successfully",
  "doctor_id": 7,
  "is_new_user": false,
  "mobile_number": "9443453525",
  "role": "user",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

---

### 1.3 Resend OTP
**POST** `/auth/otp/resend`

Resend OTP to the same mobile number. Invalidates any previously sent OTP.

**Request Body:**
```json
{
  "mobile_number": "9443453525"
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/auth/otp/resend' \
  -H 'Content-Type: application/json' \
  -d '{"mobile_number": "9443453525"}'
```

**Response (200):**
```json
{
  "success": true,
  "message": "OTP resent successfully",
  "mobile_number": "94****3525",
  "expires_in_seconds": 300
}
```

---

### 1.4 Admin OTP Verify
**POST** `/auth/admin/otp/verify`

Verify OTP for admin/operational users. The user must already exist in the `users` table with an `admin` or `operational` role.

**Request Body:**
```json
{
  "mobile_number": "9443453525",
  "otp": "123456"
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/auth/admin/otp/verify' \
  -H 'Content-Type: application/json' \
  -d '{"mobile_number": "9443453525", "otp": "123456"}'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Admin OTP verified successfully",
  "user_id": 1,
  "role": "admin",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

---

### 1.5 Google Sign-In Verify
**POST** `/auth/google/verify`

Authenticate via Google Sign-In by verifying a Firebase ID token. Finds or creates a doctor/user record by the email from the token.

**Request Body:**
```json
{
  "id_token": "eyJhbGciOiJSUz..."
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/auth/google/verify' \
  -H 'Content-Type: application/json' \
  -d '{"id_token": "eyJhbGciOiJSUz..."}'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Google sign-in successful",
  "doctor_id": 12,
  "is_new_user": true,
  "email": "doctor@gmail.com",
  "role": "user",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

---

## 2. HEALTH CHECK

### 2.1 Health Check
**GET** `/health`

Returns comprehensive health status including database and AI service checks. No auth required.

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/health'
```

**Response (200):**
```json
{
  "status": "healthy",
  "service": "doctor-onboarding-service",
  "version": "2.0.0",
  "environment": "development",
  "checks": {
    "database": {
      "status": "healthy",
      "latency_ms": 1.2,
      "message": "Connected"
    },
    "ai_service": {
      "status": "healthy",
      "message": "API key configured"
    }
  }
}
```

---

### 2.2 Liveness Probe
**GET** `/live`

Kubernetes liveness probe. Returns immediately without checking dependencies.

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/live'
```

**Response (200):**
```json
{
  "status": "alive"
}
```

---

### 2.3 Readiness Probe
**GET** `/ready`

Kubernetes readiness probe. Verifies the database connection is healthy.

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/ready'
```

**Response (200):**
```json
{
  "status": "ready"
}
```

---

## 3. DOCTORS

All endpoints require JWT authentication. Admin/Operational role required for update and bulk upload operations.

### 3.1 List Doctors
**GET** `/doctors`

Paginated list of registered doctors. When the `status` query parameter is provided, returns full onboarding information (identity, details, media, status history).

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number (1-indexed) |
| `page_size` | int | 20 | Items per page (max 100) |
| `specialization` | string | — | Filter by specialization (partial match, only without `status`) |
| `status` | string | — | Onboarding status filter: `PENDING`, `SUBMITTED`, `VERIFIED`, `REJECTED`. When set, returns full `DoctorWithFullInfoResponse` |

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/doctors?page=1&page_size=20' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Doctors retrieved successfully",
  "data": [...],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 50,
    "total_pages": 3
  }
}
```

---

### 3.2 Lookup Doctor (Admin View)
**GET** `/doctors/lookup`

Full admin view of a doctor's complete onboarding profile. Looks up by `doctor_id`, `email`, or `phone`. Aggregates data from doctors, identity, details, media, and status history tables.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `doctor_id` | int | Lookup by numeric doctor ID |
| `email` | string | Lookup by email address |
| `phone` | string | Lookup by phone number (+91…) |

> At least one parameter is required.

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/doctors/lookup?doctor_id=7' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):**
```json
{
  "identity": { "doctor_id": 7, "first_name": "John", "last_name": "Doe", ... },
  "details": { "bio": "...", "qualifications": [...], ... },
  "media": [ { "media_id": "uuid", "media_type": "image", ... } ],
  "status_history": [ { "previous_status": "PENDING", "new_status": "SUBMITTED", ... } ]
}
```

---

### 3.3 Get Doctor by ID
**GET** `/doctors/{doctor_id}`

Retrieve a single doctor's basic profile.

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/doctors/7' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Doctor retrieved successfully",
  "data": {
    "id": 7,
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@example.com",
    "phone": "+919443453525",
    "primary_specialization": "Cardiology",
    ...
  }
}
```

---

### 3.4 Update Doctor
**PUT** `/doctors/{doctor_id}`

Update an existing doctor's profile. Only provided fields are changed (partial update). Requires **Admin or Operational** role.

**Request Body:**
```json
{
  "first_name": "Updated Name",
  "primary_specialization": "Neurology"
}
```

**cURL:**
```bash
curl -X PUT 'http://127.0.0.1:6555/api/v1/doctors/7' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"first_name": "Updated Name"}'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Doctor updated successfully",
  "data": { ... }
}
```

---

### 3.5 Download CSV Template
**GET** `/doctors/bulk-upload/csv/template`

Download the official CSV template with sample rows and all supported column headers. Requires **Admin or Operational** role.

**cURL:**
```bash
curl -O 'http://127.0.0.1:6555/api/v1/doctors/bulk-upload/csv/template' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):** CSV file download (`doctor_bulk_upload_template.csv`)

---

### 3.6 Validate CSV (Dry Run)
**POST** `/doctors/bulk-upload/csv/validate`

Validate a CSV file without writing anything to the database. Returns row-level errors so the operator can fix them before confirming. Requires **Admin or Operational** role.

**Required CSV columns:** `first_name`, `last_name`, `phone`

**Max rows:** 500

**Request:** Multipart file upload (field name: `file`)

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/doctors/bulk-upload/csv/validate' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -F 'file=@doctors.csv'
```

**Response (200):**
```json
{
  "valid": true,
  "total_rows": 25,
  "error_count": 0,
  "errors": []
}
```

**Response (200) — with errors:**
```json
{
  "valid": false,
  "total_rows": 25,
  "error_count": 2,
  "errors": [
    { "row": 3, "field": "phone", "error": "Phone number is required." },
    { "row": 7, "field": "email", "error": "'bad-email' is not a valid email address." }
  ]
}
```

---

### 3.7 Confirm CSV Upload
**POST** `/doctors/bulk-upload/csv`

Confirm a previously validated CSV upload and write records to the database. Runs validation again before writing — returns `422` if any row fails. Requires **Admin or Operational** role.

**Behaviour:**
- **New doctors** (by phone) → created with `onboarding_status = PENDING` + audit entry
- **Existing doctors** (by phone) → profile fields updated; onboarding status unchanged
- Each row uses a savepoint; a DB error on one row does not affect others

**Request:** Multipart file upload (field name: `file`)

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/doctors/bulk-upload/csv' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -F 'file=@doctors.csv'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Processed 25 row(s): 20 created, 5 updated.",
  "total_rows": 25,
  "created": 20,
  "updated": 5,
  "skipped": 0,
  "rows": [
    { "row": 2, "status": "created", "doctor_id": 101, "phone": "+919443453525", "email": "dr@example.com" },
    { "row": 3, "status": "updated", "doctor_id": 7, "phone": "+919876543210", "email": null }
  ],
  "skipped_errors": []
}
```

---

## 4. DROPDOWNS

Public and authenticated endpoints for managing dropdown options (specialties, qualifications, etc.).

### 4.1 Get All Dropdown Options
**GET** `/dropdowns`

Return every supported dropdown field with its approved options. **No authentication required.**

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/dropdowns'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Dropdown options loaded successfully",
  "data": {
    "fields": {
      "specialty": {
        "field_name": "specialty",
        "description": "Medical specialty",
        "options": [
          { "id": 1, "value": "Cardiology", "label": "Cardiology", "display_order": 0 },
          { "id": 2, "value": "Neurology", "label": "Neurology", "display_order": 1 }
        ]
      },
      "qualifications": { ... },
      "languages_spoken": { ... }
    },
    "supported_fields": ["age_groups_treated", "conditions_treated", "fellowships", ...]
  }
}
```

**Supported fields:** `specialty`, `sub_specialties`, `qualifications`, `fellowships`, `professional_memberships`, `languages_spoken`, `age_groups_treated`, `primary_practice_location`, `practice_segments`, `training_experience`, `motivation_in_practice`, `unwinding_after_work`, `quality_time_interests`, `conditions_treated`, `procedures_performed`

---

### 4.2 Get Dropdown Options for a Single Field
**GET** `/dropdowns/{field_name}`

Return approved options for one specific dropdown field. **No authentication required.**

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/dropdowns/specialty'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Options for 'specialty' loaded successfully",
  "data": {
    "field_name": "specialty",
    "description": "Medical specialty",
    "options": [
      { "id": 1, "value": "Cardiology", "label": "Cardiology", "display_order": 0 }
    ]
  }
}
```

---

### 4.3 Submit New Dropdown Option
**POST** `/dropdowns/submit`

Propose a new dropdown value. Stored as `pending` until an admin approves it. Requires **JWT authentication** (any role).

**Request Body:**
```json
{
  "field_name": "specialty",
  "value": "Sports Medicine",
  "label": "Sports Medicine"
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/dropdowns/submit' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"field_name": "specialty", "value": "Sports Medicine"}'
```

**Response (202):**
```json
{
  "success": true,
  "message": "'Sports Medicine' has been submitted for 'specialty' and is pending admin review.",
  "data": {
    "id": 42,
    "field_name": "specialty",
    "value": "Sports Medicine",
    "label": "Sports Medicine",
    "status": "pending",
    "message": "..."
  }
}
```

---

## 5. ONBOARDING

Endpoints for resume extraction and doctor profile verification workflow.

### 5.1 Extract Resume
**POST** `/onboarding/extract-resume`

Upload a doctor's resume (PDF or Image) and extract structured professional data using AI. **No authentication required.**

**Supported formats:** PDF, PNG, JPG, JPEG | **Max file size:** 10MB

**Request:** Multipart file upload (field name: `file`)

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/onboarding/extract-resume' \
  -F 'file=@resume.pdf'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Resume parsed successfully",
  "data": {
    "first_name": "Sarah",
    "last_name": "Johnson",
    "email": "sarah@hospital.com",
    "primary_specialization": "Cardiology",
    "qualifications": [...],
    "expertise": [...],
    ...
  },
  "processing_time_ms": 3250.15
}
```

---

### 5.2 Submit Profile for Verification
**POST** `/onboarding/submit/{doctor_id}`

Submit a doctor's profile for admin review. Requires **JWT authentication**. Regular users can only submit their own profile; admin/operational users can submit on behalf of any doctor.

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/onboarding/submit/7' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Profile submitted successfully",
  "data": {
    "doctor_id": 7,
    "previous_status": "PENDING",
    "new_status": "SUBMITTED"
  }
}
```

---

### 5.3 Get Email Template
**GET** `/onboarding/email-template/{doctor_id}`

Fetch pre-rendered email subject and body for the admin verification/rejection popup. Requires **Admin or Operational** role.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | `verified` or `rejected` |

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/onboarding/email-template/7?action=verified' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Email template loaded successfully",
  "data": {
    "action": "verified",
    "doctor_id": 7,
    "doctor_email": "john.doe@example.com",
    "subject": "Your Profile Has Been Verified",
    "body_html": "<h1>Congratulations, Dr. Doe!</h1>..."
  }
}
```

---

### 5.4 Verify Doctor Profile
**POST** `/onboarding/verify/{doctor_id}`

Mark a doctor's profile as verified. Optionally send a notification email. Requires **Admin or Operational** role.

**Request Body:**
```json
{
  "send_email": true,
  "email_subject": "Your Profile Has Been Verified",
  "email_body": "<h1>Congratulations!</h1>..."
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/onboarding/verify/7' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"send_email": true}'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Profile verified successfully",
  "data": {
    "doctor_id": 7,
    "previous_status": "SUBMITTED",
    "new_status": "VERIFIED",
    "verified_at": "2026-02-28T17:30:00Z",
    "email_sent": true
  }
}
```

---

### 5.5 Reject Doctor Profile
**POST** `/onboarding/reject/{doctor_id}`

Mark a doctor's profile as rejected. Optionally provide a reason and send a notification email. Requires **Admin or Operational** role.

**Request Body:**
```json
{
  "reason": "Missing medical registration documentation",
  "send_email": true,
  "email_subject": "Profile Update Required",
  "email_body": "<h1>Action Required</h1>..."
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/onboarding/reject/7' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"reason": "Missing documentation", "send_email": true}'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Profile rejected successfully",
  "data": {
    "doctor_id": 7,
    "previous_status": "SUBMITTED",
    "new_status": "REJECTED",
    "reason": "Missing documentation",
    "email_sent": true
  }
}
```

---

## 6. VOICE ONBOARDING

Conversational AI-powered voice registration. All endpoints require JWT authentication.

### 6.1 Start Session
**POST** `/voice/start`

Start a new voice-based onboarding session. Returns a greeting and session ID.

**Supported Languages:** `en` (English), `es` (Spanish), `hi` (Hindi)

**Session Expiry:** 30 minutes of inactivity.

**Request Body:**
```json
{
  "language": "en",
  "context": null
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/voice/start' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"language": "en"}'
```

**Response (201):**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "active",
  "greeting": "Hello! I'm here to help you complete your doctor registration. Let's start with your full name.",
  "fields_total": 8,
  "created_at": "2026-02-28T17:30:00Z"
}
```

---

### 6.2 Send Chat Message
**POST** `/voice/chat`

Send a user's speech transcript and receive an AI response with extracted data.

**Request Body:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_transcript": "My name is Dr. Sarah Johnson and I specialize in Cardiology",
  "context": null
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/voice/chat' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "550e8400-...", "user_transcript": "My name is Dr. Sarah Johnson"}'
```

**Response (200):**
```json
{
  "session_id": "550e8400-...",
  "status": "active",
  "ai_response": "Nice to meet you, Dr. Johnson! I see you specialize in Cardiology. What's your medical registration number?",
  "fields_collected": 2,
  "fields_total": 8,
  "fields_status": [
    { "field_name": "name", "display_name": "Full Name", "is_collected": true, "value": "Dr. Sarah Johnson", "confidence": 0.95 },
    { "field_name": "specialization", "display_name": "Specialization", "is_collected": true, "value": "Cardiology", "confidence": 0.92 }
  ],
  "current_data": { "name": "Dr. Sarah Johnson", "specialization": "Cardiology" },
  "is_complete": false,
  "turn_number": 2
}
```

---

### 6.3 Get Session Status
**GET** `/voice/session/{session_id}`

Retrieve the current status of a voice onboarding session.

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/voice/session/550e8400-...' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):**
```json
{
  "session_id": "550e8400-...",
  "status": "active",
  "language": "en",
  "fields_collected": 2,
  "fields_total": 8,
  "fields_status": [...],
  "current_data": { ... },
  "is_complete": false,
  "turn_count": 2,
  "created_at": "2026-02-28T17:30:00Z",
  "updated_at": "2026-02-28T17:32:00Z",
  "expires_at": "2026-02-28T18:02:00Z"
}
```

---

### 6.4 Finalize Session
**POST** `/voice/session/{session_id}/finalize`

Finalize a completed session and retrieve the doctor data with confidence scores. Session must have `is_complete: true`.

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/voice/session/550e8400-.../finalize' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):**
```json
{
  "session_id": "550e8400-...",
  "success": true,
  "message": "Session finalized",
  "doctor_data": {
    "name": "Dr. Sarah Johnson",
    "specialization": "Cardiology",
    "medical_registration_number": "MED123456",
    "email": "sarah.johnson@hospital.com"
  },
  "confidence_scores": {
    "name": 0.95,
    "specialization": 0.92,
    "medical_registration_number": 0.98,
    "email": 0.99
  }
}
```

---

### 6.5 Cancel Session
**DELETE** `/voice/session/{session_id}`

Cancel and delete a voice onboarding session. This is irreversible.

**cURL:**
```bash
curl -X DELETE 'http://127.0.0.1:6555/api/v1/voice/session/550e8400-...' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (204):** No content

---

## 7. ONBOARDING ADMIN

Admin CRUD endpoints for managing doctor onboarding data. All endpoints require **Admin or Operational** role.

### 7.1 Create Doctor Identity
**POST** `/onboarding-admin/identities`

Create a new `doctor_identity` record.

**Request Body:**
```json
{
  "doctor_id": 7,
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com",
  "phone_number": "+919443453525"
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/onboarding-admin/identities' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"doctor_id": 7, "first_name": "John", "last_name": "Doe", "email": "john@example.com"}'
```

**Response (201):** `DoctorIdentityResponse` object

---

### 7.2 Get Doctor Identity
**GET** `/onboarding-admin/identities`

Fetch a doctor identity by `doctor_id` or `email`.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `doctor_id` | int | Lookup by doctor ID |
| `email` | string | Lookup by email |

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/onboarding-admin/identities?doctor_id=7' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):** `DoctorIdentityResponse` object

---

### 7.3 Upsert Doctor Details
**PUT** `/onboarding-admin/details/{doctor_id}`

Create or update the `doctor_details` row for a doctor.

**Request Body:**
```json
{
  "bio": "Experienced cardiologist...",
  "qualifications": ["MD", "DM Cardiology"],
  "years_of_experience": 15
}
```

**cURL:**
```bash
curl -X PUT 'http://127.0.0.1:6555/api/v1/onboarding-admin/details/7' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"bio": "Experienced cardiologist..."}'
```

**Response (200):** `DoctorDetailsResponse` object

---

### 7.4 Get Doctor Details
**GET** `/onboarding-admin/details/{doctor_id}`

Fetch doctor details for a given doctor ID.

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/onboarding-admin/details/7' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):** `DoctorDetailsResponse` object

---

### 7.5 Add Media Record
**POST** `/onboarding-admin/media/{doctor_id}`

Insert a `doctor_media` metadata row and return the absolute file URI.

**Request Body:**
```json
{
  "media_type": "image",
  "media_category": "profile_photo",
  "file_uri": "/api/v1/blobs/7/profile_photo/abc.jpg",
  "file_name": "photo.jpg",
  "file_size": 204800,
  "mime_type": "image/jpeg"
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/onboarding-admin/media/7' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"media_type": "image", "media_category": "profile_photo", "file_uri": "...", "file_name": "photo.jpg"}'
```

**Response (201):** `DoctorMediaResponse` object

---

### 7.6 List Doctor Media
**GET** `/onboarding-admin/media/{doctor_id}`

List all media records for a doctor with absolute URIs.

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/onboarding-admin/media/7' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):** Array of `DoctorMediaResponse` objects

---

### 7.7 Delete Media Record
**DELETE** `/onboarding-admin/media/{media_id}`

Delete a doctor media record by its UUID `media_id`.

**cURL:**
```bash
curl -X DELETE 'http://127.0.0.1:6555/api/v1/onboarding-admin/media/abc-uuid-123' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (204):** No content

---

### 7.8 Upload Media File
**POST** `/onboarding-admin/media/{doctor_id}/upload`

Upload a file directly to blob storage and register its metadata. Supported: images (JPG, PNG, GIF) and documents (PDF). Max size: 50 MB.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `media_category` | string | Yes | Category key: `profile_photo`, `certificate`, `resume`, etc. |
| `field_name` | string | No | Logical field key for `media_urls` (defaults to `media_category`) |

**Request:** Multipart file upload (field name: `file`)

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/onboarding-admin/media/7/upload?media_category=profile_photo' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -F 'file=@photo.jpg'
```

**Response (201):** `DoctorMediaResponse` object

---

### 7.9 Log Status History
**POST** `/onboarding-admin/status-history/{doctor_id}`

Append a status-change entry to `doctor_status_history`.

**Request Body:**
```json
{
  "previous_status": "PENDING",
  "new_status": "SUBMITTED",
  "changed_by": "admin@example.com",
  "notes": "Profile submitted for review"
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/onboarding-admin/status-history/7' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"previous_status": "PENDING", "new_status": "SUBMITTED", "changed_by": "admin@example.com"}'
```

**Response (201):** `DoctorStatusHistoryResponse` object

---

### 7.10 Get Status History
**GET** `/onboarding-admin/status-history/{doctor_id}`

Retrieve all status history entries for a doctor.

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/onboarding-admin/status-history/7' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):** Array of `DoctorStatusHistoryResponse` objects

---

## 8. ADMIN USERS

User management for the RBAC system. Most endpoints require **Admin** role.

### 8.1 List Users
**GET** `/admin/users`

Paginated list of users with optional filtering. Requires **Admin or Operational** role.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `skip` | int | 0 | Number of records to skip |
| `limit` | int | 50 | Records per page (max 100) |
| `role` | list[string] | — | Filter by role(s): `admin`, `operational`, `user` |
| `is_active` | bool | — | Filter by active status |

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/admin/users?limit=50&is_active=true' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):**
```json
{
  "success": true,
  "users": [
    {
      "id": 1,
      "phone": "+919443453525",
      "email": "admin@example.com",
      "role": "admin",
      "is_active": true,
      "doctor_id": null,
      "created_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total": 10,
  "skip": 0,
  "limit": 50
}
```

---

### 8.2 List Admin Users
**GET** `/admin/users/admins`

List all admin users (for audit purposes). Requires **Admin** role.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `active_only` | bool | true | Only show active admins |

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/admin/users/admins' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):** Same format as List Users

---

### 8.3 Get User by ID
**GET** `/admin/users/{user_id}`

Get details of a specific user. Requires **Admin or Operational** role.

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/admin/users/1' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):** `UserResponse` object

---

### 8.4 Seed Initial Admin (No Auth)
**POST** `/admin/users/seed`

Create the first admin user when no admins exist. **No authentication required.** This endpoint is self-disabling: once at least one admin exists, it returns `403`.

**Request Body:**
```json
{
  "phone": "+919443453525",
  "email": "admin@example.com",
  "role": "admin",
  "is_active": true
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/admin/users/seed' \
  -H 'Content-Type: application/json' \
  -d '{"phone": "+919443453525", "email": "admin@example.com", "role": "admin"}'
```

**Response (201):**
```json
{
  "success": true,
  "message": "Initial admin user seeded successfully",
  "user": { ... }
}
```

---

### 8.5 Create User
**POST** `/admin/users`

Create a new user with a specified role. Requires **Admin** role.

**Request Body:**
```json
{
  "phone": "+919876543210",
  "email": "ops@example.com",
  "role": "operational",
  "is_active": true,
  "doctor_id": null
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/admin/users' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"phone": "+919876543210", "email": "ops@example.com", "role": "operational"}'
```

**Response (201):**
```json
{
  "success": true,
  "message": "User created successfully with role 'operational'",
  "user": { ... }
}
```

---

### 8.6 Update User
**PATCH** `/admin/users/{user_id}`

Update a user's details (role, active status, doctor_id). Requires **Admin** role. Cannot demote or deactivate yourself.

**Request Body:**
```json
{
  "role": "operational",
  "is_active": true,
  "doctor_id": 7
}
```

**cURL:**
```bash
curl -X PATCH 'http://127.0.0.1:6555/api/v1/admin/users/2' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"role": "operational"}'
```

**Response (200):**
```json
{
  "success": true,
  "message": "User updated successfully",
  "user": { ... }
}
```

---

### 8.7 Update User Role
**PATCH** `/admin/users/{user_id}/role`

Change a user's role. Requires **Admin** role.

**Request Body:**
```json
{
  "role": "admin"
}
```

**cURL:**
```bash
curl -X PATCH 'http://127.0.0.1:6555/api/v1/admin/users/2/role' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"role": "admin"}'
```

**Response (200):**
```json
{
  "success": true,
  "message": "User role changed from 'user' to 'admin'",
  "user": { ... }
}
```

---

### 8.8 Activate/Deactivate User
**PATCH** `/admin/users/{user_id}/status`

Activate or deactivate a user (soft action). Requires **Admin** role.

**Request Body:**
```json
{
  "is_active": false
}
```

**cURL:**
```bash
curl -X PATCH 'http://127.0.0.1:6555/api/v1/admin/users/2/status' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"is_active": false}'
```

**Response (200):**
```json
{
  "success": true,
  "message": "User deactivated successfully",
  "user": { ... }
}
```

---

### 8.9 Deactivate User (Soft Delete)
**DELETE** `/admin/users/{user_id}`

Deactivate a user. Use this instead of hard delete to preserve audit trail. Requires **Admin** role.

**cURL:**
```bash
curl -X DELETE 'http://127.0.0.1:6555/api/v1/admin/users/2' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):**
```json
{
  "success": true,
  "message": "User deactivated successfully",
  "user_id": 2
}
```

---

## 9. ADMIN DROPDOWNS

Admin management of dropdown options. All endpoints require **Admin or Operational** role.

### 9.1 List Supported Fields
**GET** `/admin/dropdowns/fields`

Return the canonical list of dropdown field names and their descriptions.

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/admin/dropdowns/fields' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Supported dropdown fields",
  "data": {
    "fields": [
      { "field_name": "specialty", "description": "Medical specialty" },
      { "field_name": "qualifications", "description": "Medical qualifications" }
    ]
  }
}
```

---

### 9.2 List All Options
**GET** `/admin/dropdowns`

List all dropdown options across all fields with optional filtering.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `field_name` | string | — | Filter by field name |
| `status` | string | — | Filter by: `approved`, `pending`, `rejected` |
| `search` | string | — | Substring match on value/label |
| `skip` | int | 0 | Pagination offset |
| `limit` | int | 50 | Items per page (max 200) |

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/admin/dropdowns?status=pending&limit=50' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Found 15 option(s)",
  "data": {
    "items": [
      {
        "id": 1,
        "field_name": "specialty",
        "value": "Sports Medicine",
        "label": "Sports Medicine",
        "status": "pending",
        "is_system": false,
        ...
      }
    ],
    "total": 15,
    "skip": 0,
    "limit": 50,
    "pending_count": 5
  }
}
```

---

### 9.3 List Pending Options
**GET** `/admin/dropdowns/pending`

Shortcut to list only pending options awaiting review.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `field_name` | string | — | Filter by field name |
| `skip` | int | 0 | Pagination offset |
| `limit` | int | 50 | Items per page (max 200) |

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/admin/dropdowns/pending' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):** Same format as List All Options (all items are `pending`)

---

### 9.4 Get Option by ID
**GET** `/admin/dropdowns/{option_id}`

Retrieve a single dropdown option by its ID.

**cURL:**
```bash
curl 'http://127.0.0.1:6555/api/v1/admin/dropdowns/42' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Dropdown option retrieved",
  "data": {
    "id": 42,
    "field_name": "specialty",
    "value": "Sports Medicine",
    "label": "Sports Medicine",
    "status": "pending",
    "is_system": false,
    "display_order": 0,
    "submitted_by": "12",
    "reviewed_by": null,
    "review_notes": null,
    "created_at": "2026-02-28T17:30:00Z"
  }
}
```

---

### 9.5 Create Option
**POST** `/admin/dropdowns`

Create a new dropdown option (approved immediately since it's admin-created).

**Request Body:**
```json
{
  "field_name": "specialty",
  "value": "Nuclear Medicine",
  "label": "Nuclear Medicine",
  "is_system": false,
  "display_order": 0
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/admin/dropdowns' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"field_name": "specialty", "value": "Nuclear Medicine"}'
```

**Response (201):**
```json
{
  "success": true,
  "message": "Option 'Nuclear Medicine' created and approved for 'specialty'",
  "data": { ... }
}
```

---

### 9.6 Update Option
**PATCH** `/admin/dropdowns/{option_id}`

Update label, display order, or review notes.

**Request Body:**
```json
{
  "label": "Updated Label",
  "display_order": 5,
  "review_notes": "Corrected spelling"
}
```

**cURL:**
```bash
curl -X PATCH 'http://127.0.0.1:6555/api/v1/admin/dropdowns/42' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"label": "Updated Label"}'
```

**Response (200):** Updated `DropdownOptionResponse` object

---

### 9.7 Delete Option
**DELETE** `/admin/dropdowns/{option_id}`

Delete a dropdown option. System-seeded options (`is_system=true`) cannot be deleted.

**cURL:**
```bash
curl -X DELETE 'http://127.0.0.1:6555/api/v1/admin/dropdowns/42' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Dropdown option 42 deleted successfully",
  "data": { "option_id": 42, "deleted": true }
}
```

---

### 9.8 Approve Option
**POST** `/admin/dropdowns/{option_id}/approve`

Approve a pending dropdown option. Once approved, it appears in public dropdowns.

**Request Body:**
```json
{
  "review_notes": "Looks good"
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/admin/dropdowns/42/approve' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"review_notes": "Approved"}'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Option 'Sports Medicine' approved for 'specialty'",
  "data": { ... }
}
```

---

### 9.9 Reject Option
**POST** `/admin/dropdowns/{option_id}/reject`

Reject a pending dropdown option. Rejected options remain in the database for audit purposes.

**Request Body:**
```json
{
  "review_notes": "Duplicate of existing option"
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/admin/dropdowns/42/reject' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"review_notes": "Duplicate"}'
```

**Response (200):**
```json
{
  "success": true,
  "message": "Option 'Sports Medicine' rejected for 'specialty'",
  "data": { ... }
}
```

---

### 9.10 Bulk Approve
**POST** `/admin/dropdowns/bulk-approve`

Approve multiple pending options at once (max 200 per request).

**Request Body:**
```json
{
  "option_ids": [42, 43, 44],
  "review_notes": "Batch approved"
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/admin/dropdowns/bulk-approve' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"option_ids": [42, 43, 44]}'
```

**Response (200):**
```json
{
  "success": true,
  "message": "3 option(s) approved successfully",
  "data": {
    "action": "approved",
    "updated_count": 3,
    "review_notes": "Batch approved"
  }
}
```

---

### 9.11 Bulk Reject
**POST** `/admin/dropdowns/bulk-reject`

Reject multiple pending options at once (max 200 per request).

**Request Body:**
```json
{
  "option_ids": [45, 46],
  "review_notes": "Duplicates"
}
```

**cURL:**
```bash
curl -X POST 'http://127.0.0.1:6555/api/v1/admin/dropdowns/bulk-reject' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"option_ids": [45, 46], "review_notes": "Duplicates"}'
```

**Response (200):**
```json
{
  "success": true,
  "message": "2 option(s) rejected successfully",
  "data": {
    "action": "rejected",
    "updated_count": 2,
    "review_notes": "Duplicates"
  }
}
```

---

## 10. ADDITIONAL REFERENCE

### Authentication Details

All endpoints (except Health, public Dropdowns, Resume Extraction, and Admin Seed) require a **JWT Bearer Token**:

```
Authorization: Bearer <access_token>
```

Obtain a token via `/auth/otp/verify`, `/auth/admin/otp/verify`, or `/auth/google/verify`.

**Interactive API Docs:**
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

---

### CSV Bulk Upload — Detailed Workflow

All three CSV endpoints require **Admin or Operational** role.

**Auth chain:**
```
Bearer token
  └── require_authentication()   [JWT signature + expiry check]
        └── get_current_user()   [load User from DB, check is_active]
              └── require_admin_or_operational()  [role ∈ {admin, operational}]
```

**Two-Phase Workflow:**
```
Step 1  POST /doctors/bulk-upload/csv/validate   ← upload CSV, get ALL row errors
           │
           ├── errors found  → fix CSV, repeat Step 1
           │
           └── valid=true, errors=[]
                    │
Step 2  POST /doctors/bulk-upload/csv           ← upload clean CSV, write to DB
           │
           ├── rows created with onboarding_status = PENDING
           └── audit entry added to doctor_status_history
```

| Constraint | Value |
|------------|-------|
| Max rows | 500 |
| Encoding | UTF-8 (BOM stripped automatically) |
| Multi-value fields | Pipe-separated: `English\|Hindi\|Marathi` |
| Required columns | `first_name`, `last_name`, `phone` |
| Phone normalisation | Auto-converted to E.164 `+91XXXXXXXXXX` |

**Validated fields per row:**

| Field | Validation |
|-------|-----------|
| `phone` | Required; digits only ≥ 10; normalised to `+91…` |
| `first_name` | Required; non-empty |
| `last_name` | Required; non-empty |
| `email` | Optional; must contain `@` and a dot in domain |
| `years_of_experience` | Optional; numeric 0–100 |
| `consultation_fee` | Optional; numeric ≥ 0 |
| `registration_year` | Optional; numeric 1900–2100 |
| `year_of_mbbs` | Optional; numeric 1900–2100 |
| `year_of_specialisation` | Optional; numeric 1900–2100 |
| `years_of_clinical_experience` | Optional; numeric 0–100 |
| `years_post_specialisation` | Optional; numeric 0–100 |

**Per-row behaviour on confirm upload:**
- **New doctor** (no existing record with that phone): Creates `doctors` + `doctor_identity` (PENDING) + `doctor_status_history` audit entry
- **Existing doctor** (phone already in DB): Updates profile fields; onboarding status unchanged
- **DB-level error** (e.g. unique constraint): Row rolled back via savepoint; others continue

---

### Admin Verification & Email Notifications — Detailed Flow

When an admin verifies or rejects a doctor's profile, the backend optionally sends an email:

1. **Admin opens popup** → frontend fetches pre-filled template via `GET /onboarding/email-template/{doctor_id}?action=verified|rejected`
2. **Admin edits** subject/body if desired
3. **Admin clicks Send** → frontend calls `POST /onboarding/verify/{doctor_id}` or `POST /onboarding/reject/{doctor_id}`

**Verify payload fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `send_email` | bool | false | Trigger email delivery |
| `email_subject` | string \| null | null | Admin-edited subject; template default if omitted |
| `email_body` | string \| null | null | Admin-edited HTML body; template default if omitted |

**Reject payload** adds `reason` (string \| null) for the rejection reason.

> **Non-blocking email**: If SMTP fails, the status change is **not rolled back**. Response includes `"email_sent": false` and `"email_error"`.

**Email template placeholders** (configured in `config/email_templates.yaml`):

| Placeholder | Description |
|-------------|-------------|
| `{doctor_name}` | Full name with title |
| `{first_name}` | Doctor's first name |
| `{medical_registration_number}` | MRN on file |
| `{specialization}` | Primary specialisation |
| `{reason}` | Rejection reason (reject template only) |
| `{platform_name}` | From `EMAIL_FROM_NAME` env variable |
| `{support_email}` | From `EMAIL_FROM_ADDRESS` env variable |

---

### Dropdown Approval Workflow

The platform manages dropdown options through a **3-status approval workflow**:

| Status | Visible in public dropdowns? | Created by |
|--------|------------------------------|------------|
| `approved` | ✅ Yes | Admin direct-create or approved user submission |
| `pending` | ❌ No — hidden until reviewed | Doctor/user `POST /dropdowns/submit` |
| `rejected` | ❌ Never | Admin reject action |

**Supported fields:** `specialty`, `sub_specialties`, `qualifications`, `fellowships`, `professional_memberships`, `languages_spoken`, `age_groups_treated`, `primary_practice_location`, `practice_segments`, `training_experience`, `motivation_in_practice`, `unwinding_after_work`, `quality_time_interests`, `conditions_treated`, `procedures_performed`

---

### Standard Response Format

**Success:**
```json
{
  "success": true,
  "message": "Operation successful",
  "data": { }
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
    "total": 100,
    "total_pages": 5
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

---

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

---

### Rate Limits

| Endpoint Type | Limit |
|--------------|-------|
| OTP Request | 3 per minute per phone |
| OTP Verify | 5 attempts per OTP |
| Resume Extraction | 10 per minute |
| Voice Chat | 60 per minute per session |
| Admin APIs | 100 per minute |
