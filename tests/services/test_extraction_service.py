"""Unit tests for Resume Extraction Service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.app.core.exceptions import ExtractionError, FileValidationError
from src.app.services.extraction_service import ResumeExtractionService


@pytest.fixture
def mock_gemini():
    return AsyncMock()

@pytest.fixture
def mock_prompt_manager():
    manager = MagicMock()
    manager.get_resume_extraction_prompt.return_value = "Test prompt"
    return manager

@pytest.fixture
def extraction_service(mock_gemini, mock_prompt_manager):
    with patch("src.app.services.extraction_service.get_gemini_service", return_value=mock_gemini):
        with patch("src.app.services.extraction_service.get_prompt_manager", return_value=mock_prompt_manager):
            return ResumeExtractionService()

def test_get_mime_type_success(extraction_service):
    assert extraction_service._get_mime_type("test.pdf") == "application/pdf"
    assert extraction_service._get_mime_type("test.png") == "image/png"
    assert extraction_service._get_mime_type("test.jpg") == "image/jpeg"

def test_get_mime_type_failure(extraction_service):
    with pytest.raises(FileValidationError) as exc:
        extraction_service._get_mime_type("test.txt")
    assert "Unsupported file type" in str(exc.value)

@pytest.mark.asyncio
async def test_extract_from_file_success(extraction_service, mock_gemini):
    mock_gemini.generate_with_vision.return_value = {
        "personal_details": {"first_name": "Test", "last_name": "Doctor"},
        "professional_information": {"primary_specialization": "General"},
    }

    data, time_ms = await extraction_service.extract_from_file(b"dummy", "resume.pdf")

    assert data.personal_details.first_name == "Test"
    assert time_ms > 0
    mock_gemini.generate_with_vision.assert_called_once()


@pytest.mark.asyncio
async def test_extract_from_file_keeps_section1_and_section2_fields(
    extraction_service, mock_gemini
):
    """All Section 1 + Section 2 fields from Gemini must survive Pydantic parsing."""
    mock_gemini.generate_with_vision.return_value = {
        "personal_details": {
            "title": "Dr.",
            "first_name": "Asha",
            "last_name": "Rao",
            "email": "asha@example.com",
            "phone": "+919876543210",
        },
        "professional_information": {
            "primary_specialization": "Cardiology",
            "years_of_experience": 12,
            "languages": ["English", "Hindi"],
        },
        "registration": {
            "medical_registration_number": "REG-998",
            "medical_council": "Maharashtra Medical Council",
            "registration_year": 2011,
        },
        "qualifications": [
            {"degree": "MBBS", "institution": "AIIMS", "year": 2008},
            {"degree": "MD Cardiology", "institution": "PGI", "year": 2012},
        ],
        "achievements": {
            "awards_recognition": ["Best Resident 2010"],
            "memberships": ["Indian Medical Association"],
            "fellowships": ["FRCS"],
        },
    }

    data, _ = await extraction_service.extract_from_file(b"dummy", "resume.pdf")

    assert data.personal_details.title == "Dr."
    assert data.personal_details.first_name == "Asha"
    assert data.personal_details.last_name == "Rao"
    assert data.professional_information.years_of_experience == 12
    assert data.professional_information.languages == ["English", "Hindi"]
    assert data.registration.medical_council == "Maharashtra Medical Council"
    assert data.qualifications[0].degree == "MBBS"
    assert data.qualifications[0].year == 2008
    assert data.achievements.fellowships == ["FRCS"]
    assert data.achievements.awards_recognition == ["Best Resident 2010"]
    assert data.achievements.memberships == ["Indian Medical Association"]

@pytest.mark.asyncio
async def test_extract_from_file_routes_docx_through_text_path(
    extraction_service, mock_gemini
):
    """Word documents must use the text path, not Gemini Vision."""
    mock_gemini.generate_structured.return_value = {
        "personal_details": {"first_name": "Word", "last_name": "Doc"},
    }

    with patch(
        "src.app.services.extraction_service.extract_text_from_document",
        return_value="Dr Word Doc\nCardiology",
    ) as mock_text:
        data, time_ms = await extraction_service.extract_from_file(
            b"docx-bytes", "resume.docx"
        )

    mock_text.assert_called_once_with(b"docx-bytes", "docx")
    mock_gemini.generate_structured.assert_called_once()
    mock_gemini.generate_with_vision.assert_not_called()
    assert data.personal_details.first_name == "Word"
    assert time_ms > 0


@pytest.mark.asyncio
async def test_extract_from_file_failure(extraction_service, mock_gemini):
    mock_gemini.generate_with_vision.side_effect = Exception("API Error")

    with pytest.raises(ExtractionError) as exc:
        await extraction_service.extract_from_file(b"dummy", "resume.pdf")
    assert "Failed to extract" in str(exc.value)

@pytest.mark.asyncio
async def test_extract_from_text_success(extraction_service, mock_gemini):
    mock_gemini.generate_structured.return_value = {
        "personal_details": {"first_name": "Test", "last_name": "Doctor"},
        "professional_information": {"primary_specialization": "General"},
    }

    data, time_ms = await extraction_service.extract_from_text("Dummy resume content")

    assert data.personal_details.first_name == "Test"
    assert time_ms > 0
    mock_gemini.generate_structured.assert_called_once()

@pytest.mark.asyncio
async def test_extract_from_text_failure(extraction_service, mock_gemini):
    mock_gemini.generate_structured.side_effect = Exception("API Error")

    with pytest.raises(ExtractionError) as exc:
        await extraction_service.extract_from_text("Dummy content")
    assert "Failed to extract" in str(exc.value)
