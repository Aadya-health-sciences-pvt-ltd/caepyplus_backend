"""Contract tests for LinQMD user payload mapping."""
from __future__ import annotations

from src.app.services.linqmd_sync_service import LinQMDUserPayload, LinQMDSyncService


class TestLinQMDUserPayloadFormData:
    def test_create_includes_required_fields_and_theme(self):
        payload = LinQMDUserPayload(
            name="cardiology-bangalore-drmurali",
            mail="dr@example.com",
            password="VelvetHorizon742!",
            fullname="Dr Murali Mohan",
            phone_number="+919876543210",
            speciality="Cardiology",
            theme="dp_1",
        )

        form = payload.to_form_data(include_theme=True)

        assert form["name"] == "cardiology-bangalore-drmurali"
        assert form["mail"] == "dr@example.com"
        assert form["pass"] == "VelvetHorizon742!"
        assert form["theme"] == "dp_1"
        assert form["fullname"] == "Dr Murali Mohan"
        assert form["phone_number"] == "+919876543210"
        assert form["speciality"] == "Cardiology"

    def test_update_omits_theme(self):
        payload = LinQMDUserPayload(
            name="cardiology-bangalore-drmurali",
            mail="dr@example.com",
            password="secret",
            fullname="Dr Murali",
            phone_number="+919876543210",
            theme="dp_2",
        )

        form = payload.to_form_data(include_theme=False)

        assert "theme" not in form
        assert form["mail"] == "dr@example.com"

    def test_empty_optional_fields_are_omitted(self):
        payload = LinQMDUserPayload(
            name="user",
            mail="u@example.com",
            password="pass",
            fullname="Name",
            phone_number="",
            degree="",
            overview="",
        )

        form = payload.to_form_data(include_theme=True)

        assert "degree" not in form
        assert "overview" not in form
        assert "phone_number" not in form


class TestTransformDoctorData:
    def test_maps_identity_and_details_to_linqmd_payload(self):
        service = LinQMDSyncService()
        identity = {
            "doctor_id": 7,
            "full_name": "Dr Anjali Sharma",
            "email": "anjali@example.com",
            "phone_number": "+919111111111",
        }
        details = {
            "speciality": "Cardiology",
            "primary_practice_location": "Bangalore",
            "qualifications": [
                {"degree": "MBBS", "institution": "AIIMS", "year": 2008},
                "MD Cardiology",
            ],
            "years_post_specialisation": 10,
            "awards_academic_honours": ["Best Resident"],
            "areas_of_expertise": ["Interventional Cardiology"],
            "conditions_treated": ["Hypertension"],
            "professional_overview": "Experienced cardiologist.",
        }

        payload = service.transform_doctor_data(
            identity,
            details,
            linqmd_username="cardiology-bangalore-dranjali",
            linqmd_password="FixedPass123!",
            include_theme=False,
        )

        assert payload.name == "cardiology-bangalore-dranjali"
        assert payload.mail == "anjali@example.com"
        assert payload.password == "FixedPass123!"
        assert payload.fullname == "Dr Anjali Sharma"
        assert payload.degree == "MBBS, MD Cardiology"
        assert "MBBS - AIIMS (2008)" in payload.education_details
        assert payload.yearsofexperiences == "10"
        assert payload.awards_honors == "Best Resident"
        assert payload.overview == "Experienced cardiologist."
        assert "Interventional Cardiology" in payload.expertise_summary

    def test_generates_username_from_profile_fields(self):
        service = LinQMDSyncService()
        identity = {
            "full_name": "Dr Murali Mohan Selvam",
            "email": "murali@example.com",
        }
        details = {
            "speciality": "Cardiology",
            "primary_practice_location": "Bangalore",
        }

        payload = service.transform_doctor_data(identity, details, include_theme=False)

        assert payload.name == "cardiology-bangalore-drmurali-mohan-selvam"


class TestGenerateUsername:
    def test_honorific_merges_with_next_word(self):
        service = LinQMDSyncService()
        username = service._generate_username(
            "Cardiology",
            "Bangalore",
            "Dr Murali Mohan Selvam",
        )
        assert username == "cardiology-bangalore-drmurali-mohan-selvam"

    def test_email_fallback_when_slug_too_short(self):
        service = LinQMDSyncService()
        username = service._generate_username("", "", "", "doctor.user@example.com")
        assert username == "doctor.user"


class TestFinalizeSyncResult:
    def test_success_when_2xx_without_error_field(self):
        service = LinQMDSyncService()
        result = service._finalize_sync_result(
            42,
            200,
            {"uid": "99", "Username": "dr-x", "Password": "pw"},
        )
        assert result.success is True
        assert result.doctor_id == 42
        assert result.linqmd_response["uid"] == "99"

    def test_failure_when_api_returns_error_in_body(self):
        service = LinQMDSyncService()
        result = service._finalize_sync_result(
            42,
            200,
            {"error": "Username already exists"},
        )
        assert result.success is False
        assert result.error_message == "Username already exists"

    def test_failure_when_non_2xx_status(self):
        service = LinQMDSyncService()
        result = service._finalize_sync_result(42, 400, {"message": "Bad request"})
        assert result.success is False
        assert result.error_message == "Bad request"
