# Database Schema Documentation

*Auto-generated from current SQLAlchemy models.* 

## Table: `doctors`

| Column | Type | Nullable | Primary / Foreign Key |
|--------|------|----------|-----------------------|
| `id` | `INTEGER` | No | PK |
| `email` | `VARCHAR(100)` | Yes |  |
| `phone` | `VARCHAR(20)` | Yes |  |
| `role` | `VARCHAR(20)` | No |  |
| `onboarding_status` | `VARCHAR(20)` | No |  |
| `full_name` | `VARCHAR(200)` | Yes |  |
| `specialty` | `VARCHAR(100)` | Yes |  |
| `primary_practice_location` | `VARCHAR(100)` | Yes |  |
| `centres_of_practice` | `JSON` | No |  |
| `years_of_clinical_experience` | `INTEGER` | Yes |  |
| `years_post_specialisation` | `INTEGER` | Yes |  |
| `year_of_mbbs` | `INTEGER` | Yes |  |
| `year_of_specialisation` | `INTEGER` | Yes |  |
| `fellowships` | `JSON` | No |  |
| `qualifications` | `JSON` | No |  |
| `professional_memberships` | `JSON` | No |  |
| `awards_academic_honours` | `JSON` | No |  |
| `areas_of_clinical_interest` | `JSON` | No |  |
| `practice_segments` | `VARCHAR(50)` | Yes |  |
| `conditions_commonly_treated` | `JSON` | No |  |
| `conditions_known_for` | `JSON` | No |  |
| `conditions_want_to_treat_more` | `JSON` | No |  |
| `training_experience` | `JSON` | No |  |
| `motivation_in_practice` | `JSON` | No |  |
| `unwinding_after_work` | `JSON` | No |  |
| `recognition_identity` | `JSON` | No |  |
| `quality_time_interests` | `JSON` | No |  |
| `quality_time_interests_text` | `TEXT` | Yes |  |
| `professional_achievement` | `TEXT` | Yes |  |
| `personal_achievement` | `TEXT` | Yes |  |
| `professional_aspiration` | `TEXT` | Yes |  |
| `personal_aspiration` | `TEXT` | Yes |  |
| `what_patients_value_most` | `TEXT` | Yes |  |
| `approach_to_care` | `TEXT` | Yes |  |
| `availability_philosophy` | `TEXT` | Yes |  |
| `content_seeds` | `JSON` | No |  |
| `primary_specialization` | `TEXT` | Yes |  |
| `years_of_experience` | `INTEGER` | Yes |  |
| `consultation_fee` | `FLOAT` | Yes |  |
| `consultation_currency` | `VARCHAR(10)` | Yes |  |
| `medical_registration_number` | `VARCHAR(100)` | Yes |  |
| `medical_council` | `VARCHAR(200)` | Yes |  |
| `registration_year` | `INTEGER` | Yes |  |
| `registration_authority` | `VARCHAR(100)` | Yes |  |
| `conditions_treated` | `JSON` | No |  |
| `languages` | `JSON` | No |  |
| `practice_locations` | `JSON` | No |  |
| `onboarding_source` | `VARCHAR(50)` | Yes |  |
| `resume_url` | `VARCHAR(500)` | Yes |  |
| `profile_photo` | `VARCHAR(500)` | Yes |  |
| `verbal_intro_file` | `VARCHAR(500)` | Yes |  |
| `professional_documents` | `JSON` | No |  |
| `achievement_images` | `JSON` | No |  |
| `external_links` | `JSON` | No |  |
| `raw_extraction_data` | `JSON` | Yes |  |
| `created_at` | `DATETIME` | No |  |
| `updated_at` | `DATETIME` | Yes |  |


## Table: `doctor_identity`

| Column | Type | Nullable | Primary / Foreign Key |
|--------|------|----------|-----------------------|
| `id` | `VARCHAR(36)` | No | PK |
| `doctor_id` | `BIGINT` | No |  |
| `full_name` | `VARCHAR(200)` | No |  |
| `email` | `VARCHAR(255)` | No |  |
| `phone_number` | `VARCHAR(20)` | No |  |
| `onboarding_status` | `VARCHAR(9)` | No |  |
| `status_updated_at` | `DATETIME` | Yes |  |
| `status_updated_by` | `VARCHAR(36)` | Yes |  |
| `rejection_reason` | `TEXT` | Yes |  |
| `verified_at` | `DATETIME` | Yes |  |
| `is_active` | `BOOLEAN` | No |  |
| `registered_at` | `DATETIME` | No |  |
| `created_at` | `DATETIME` | No |  |
| `updated_at` | `DATETIME` | No |  |
| `deleted_at` | `DATETIME` | Yes |  |


## Table: `doctor_media`

| Column | Type | Nullable | Primary / Foreign Key |
|--------|------|----------|-----------------------|
| `media_id` | `VARCHAR(36)` | No | PK |
| `doctor_id` | `BIGINT` | No | FK -> doctor_identity.doctor_id |
| `field_name` | `VARCHAR(100)` | Yes |  |
| `media_type` | `VARCHAR(50)` | No |  |
| `media_category` | `VARCHAR(50)` | No |  |
| `file_uri` | `TEXT` | No |  |
| `file_name` | `VARCHAR(255)` | No |  |
| `file_size` | `BIGINT` | Yes |  |
| `mime_type` | `VARCHAR(100)` | Yes |  |
| `is_primary` | `BOOLEAN` | No |  |
| `upload_date` | `DATETIME` | No |  |
| `metadata` | `JSON` | No |  |


## Table: `doctor_status_history`

| Column | Type | Nullable | Primary / Foreign Key |
|--------|------|----------|-----------------------|
| `history_id` | `VARCHAR(36)` | No | PK |
| `doctor_id` | `BIGINT` | No | FK -> doctor_identity.doctor_id |
| `previous_status` | `VARCHAR(9)` | Yes |  |
| `new_status` | `VARCHAR(9)` | No |  |
| `changed_by` | `VARCHAR(36)` | Yes |  |
| `changed_by_email` | `VARCHAR(255)` | Yes |  |
| `rejection_reason` | `TEXT` | Yes |  |
| `notes` | `TEXT` | Yes |  |
| `ip_address` | `VARCHAR(50)` | Yes |  |
| `user_agent` | `TEXT` | Yes |  |
| `changed_at` | `DATETIME` | No |  |


## Table: `dropdown_options`

| Column | Type | Nullable | Primary / Foreign Key |
|--------|------|----------|-----------------------|
| `id` | `INTEGER` | No | PK |
| `field_name` | `VARCHAR(100)` | No |  |
| `value` | `VARCHAR(255)` | No |  |
| `label` | `VARCHAR(255)` | Yes |  |
| `status` | `VARCHAR(8)` | No |  |
| `is_system` | `BOOLEAN` | No |  |
| `display_order` | `INTEGER` | No |  |
| `submitted_by` | `VARCHAR(36)` | Yes |  |
| `submitted_by_email` | `VARCHAR(255)` | Yes |  |
| `reviewed_by` | `VARCHAR(36)` | Yes |  |
| `reviewed_by_email` | `VARCHAR(255)` | Yes |  |
| `reviewed_at` | `DATETIME` | Yes |  |
| `review_notes` | `TEXT` | Yes |  |
| `created_at` | `DATETIME` | No |  |
| `updated_at` | `DATETIME` | No |  |


## Table: `users`

| Column | Type | Nullable | Primary / Foreign Key |
|--------|------|----------|-----------------------|
| `id` | `INTEGER` | No | PK |
| `phone` | `VARCHAR(20)` | Yes |  |
| `email` | `VARCHAR(255)` | Yes |  |
| `role` | `VARCHAR(20)` | No |  |
| `is_active` | `BOOLEAN` | No |  |
| `doctor_id` | `INTEGER` | Yes | FK -> doctors.id |
| `created_at` | `DATETIME` | No |  |
| `updated_at` | `DATETIME` | Yes |  |
| `last_login_at` | `DATETIME` | Yes |  |


