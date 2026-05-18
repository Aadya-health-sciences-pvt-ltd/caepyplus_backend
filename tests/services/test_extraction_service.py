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
