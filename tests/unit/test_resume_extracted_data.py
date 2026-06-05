"""Unit tests for the ResumeExtractedData schema.

Guards the contract between the Gemini extraction prompt
(`config/prompts.yaml`) and the Pydantic schema the frontend consumes,
ensuring all Section 1 (Professional Identity) and Section 2 (Credentials)
fields survive parsing.
"""
from __future__ import annotations

from src.app.schemas.doctor import ResumeExtractedData


def _full_gemini_payload() -> dict:
    """A representative payload matching the prompt's response_schema."""
    return {
        "personal_details": {
            "title": "Dr.",
            "gender": "Female",
            "first_name": "Asha",
            "last_name": "Rao",
            "email": "asha.rao@example.com",
            "phone": "+919876543210",
        },
        "professional_information": {
            "primary_specialization": "Cardiology",
            "sub_specialties": ["Interventional Cardiology"],
            "areas_of_expertise": ["Angioplasty"],
            "years_of_experience": 12,
            "conditions_treated": ["Hypertension"],
            "procedures_performed": ["Stenting"],
            "age_groups_treated": ["Adults"],
            "languages": ["English", "Hindi"],
        },
        "registration": {
            "medical_registration_number": "REG-998",
            "medical_council": "Maharashtra Medical Council",
            "registration_year": 2011,
            "registration_authority": "MMC",
        },
        "qualifications": [
            {"degree": "MBBS", "institution": "AIIMS", "year": 2008},
            {"degree": "MD Cardiology", "institution": "PGI", "year": 2012},
        ],
        "achievements": {
            "awards_recognition": ["Best Resident 2010"],
            "memberships": ["Indian Medical Association"],
            "fellowships": ["FRCS"],
            "publications": ["Some paper"],
        },
        "media": {
            "verbal_intro_file": None,
            "professional_documents": [],
            "achievement_images": [],
            "external_links": [],
        },
        "practice_locations": [
            {
                "hospital_name": "City Hospital",
                "address": "12 MG Road",
                "city": "Mumbai",
                "state": "Maharashtra",
                "phone_number": "+912212345678",
                "consultation_fee": 500,
                "consultation_type": "In-person",
                "weekly_schedule": "Mon-Fri 10-1",
            }
        ],
    }


def test_section1_fields_survive_parsing() -> None:
    data = ResumeExtractedData(**_full_gemini_payload())

    assert data.personal_details.title == "Dr."
    assert data.personal_details.first_name == "Asha"
    assert data.personal_details.last_name == "Rao"
    assert data.personal_details.email == "asha.rao@example.com"
    assert data.personal_details.phone == "+919876543210"
    assert data.professional_information.primary_specialization == "Cardiology"
    assert data.professional_information.languages == ["English", "Hindi"]
    assert data.registration.medical_registration_number == "REG-998"
    assert data.registration.medical_council == "Maharashtra Medical Council"
    assert data.practice_locations[0].hospital_name == "City Hospital"
    assert data.practice_locations[0].city == "Mumbai"


def test_section2_fields_survive_parsing() -> None:
    data = ResumeExtractedData(**_full_gemini_payload())

    assert [q.degree for q in data.qualifications] == ["MBBS", "MD Cardiology"]
    assert data.qualifications[0].year == 2008
    assert data.qualifications[1].year == 2012
    assert data.professional_information.years_of_experience == 12
    assert data.registration.registration_year == 2011
    assert data.achievements.fellowships == ["FRCS"]
    assert data.achievements.awards_recognition == ["Best Resident 2010"]
    assert data.achievements.memberships == ["Indian Medical Association"]


def test_extra_prompt_only_fields_are_ignored() -> None:
    """Fields present in the prompt but not the schema must not break parsing."""
    data = ResumeExtractedData(**_full_gemini_payload())

    # publications / sub_specialties etc. are dropped, parsing still succeeds.
    assert not hasattr(data.achievements, "publications")


def test_defaults_when_sections_missing() -> None:
    data = ResumeExtractedData()

    assert data.personal_details.first_name is None
    assert data.professional_information.languages == []
    assert data.achievements.fellowships == []
    assert data.qualifications == []
    assert data.practice_locations == []
