"""
Resume Extraction Service.

Handles extraction of structured doctor information from uploaded
resumes (PDF, images) using Google Gemini Vision API.

Uses external prompts loaded via PromptManager (no hardcoded prompts).
"""
from __future__ import annotations

import logging
import time

from ..core.config import get_settings
from ..core.exceptions import AIServiceError, ExtractionError, FileValidationError
from ..core.prompts import get_prompt_manager
from ..schemas.doctor import ResumeExtractedData
from .document_extraction import OFFICE_EXTENSIONS, extract_text_from_document
from .gemini_service import (
    gemini_auth_log_label,
    gemini_remediation_hint,
    get_gemini_service,
)

logger = logging.getLogger(__name__)

_RESUME_MODEL_CONFIG_KEY = "GEMINI_RESUME_MODEL"


class ResumeExtractionService:
    """
    Service for extracting structured data from doctor resumes.
    
    Uses Gemini Vision API to process PDF and image documents,
    extracting professional information into a standardized format.
    
    All prompts are loaded from external configuration via PromptManager.
    """

    # Supported MIME types
    MIME_TYPES: dict[str, str] = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
    }

    def __init__(self) -> None:
        """Initialize with dependencies."""
        self.gemini = get_gemini_service()
        self.prompt_manager = get_prompt_manager()

    def _get_mime_type(self, filename: str) -> str:
        """
        Determine MIME type from filename extension.
        
        Args:
            filename: Original filename
            
        Returns:
            MIME type string
            
        Raises:
            FileValidationError: If file type is not supported
        """
        extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        mime_type = self.MIME_TYPES.get(extension)

        if not mime_type:
            raise FileValidationError(
                message=f"Unsupported file type: {extension}",
                filename=filename,
                allowed_types=list(self.MIME_TYPES.keys()),
            )

        return mime_type

    def _get_extraction_prompt(self) -> str:
        """
        Get the extraction prompt from external configuration.
        
        Combines system prompt, response schema, and instruction.
        """
        return self.prompt_manager.get_resume_extraction_prompt()

    async def extract_from_file(
        self,
        file_content: bytes,
        filename: str,
    ) -> tuple[ResumeExtractedData, float]:
        """
        Extract structured data from an uploaded resume file.
        
        Args:
            file_content: Raw bytes of the uploaded file
            filename: Original filename (used to determine MIME type)
            
        Returns:
            Tuple of (extracted_data, processing_time_ms)
            
        Raises:
            FileValidationError: If file type is not supported
            ExtractionError: If data extraction fails
            AIServiceError: If AI service is unavailable
        """
        extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        settings = get_settings()
        extraction_path = "text" if extension in OFFICE_EXTENSIONS else "vision"
        logger.info(
            "Resume extraction starting: filename=%s extension=%s path=%s "
            "model=%s %s file_size_bytes=%d",
            filename,
            extension or "<none>",
            extraction_path,
            settings.GEMINI_RESUME_MODEL,
            gemini_auth_log_label(settings),
            len(file_content),
        )

        # Word documents are not supported by Gemini Vision — extract their text
        # first and run the text-based extraction path instead.
        if extension in OFFICE_EXTENSIONS:
            document_text = extract_text_from_document(file_content, extension)
            logger.info(
                "Extracted %d chars of text from %s for resume parsing",
                len(document_text),
                filename,
            )
            return await self.extract_from_text(document_text)

        start_time = time.time()

        mime_type = self._get_mime_type(filename)

        logger.info("Extracting data from %s (%s)", filename, mime_type)

        try:
            # Get prompt from external config
            extraction_prompt = self._get_extraction_prompt()

            # Call Gemini Vision API
            parsed_data = await self.gemini.generate_with_vision(
                prompt=extraction_prompt,
                file_content=file_content,
                mime_type=mime_type,
                temperature=0.1,  # Low temperature for consistent extraction
                max_tokens=settings.GEMINI_RESUME_MAX_TOKENS,
                model=settings.GEMINI_RESUME_MODEL,
                config_key=_RESUME_MODEL_CONFIG_KEY,
                json_mode=True,
            )

            # Validate and create response object
            extracted_data = ResumeExtractedData(**parsed_data)

            processing_time = (time.time() - start_time) * 1000

            logger.info("Successfully extracted data from %s in %.2fms", filename, processing_time)

            return extracted_data, processing_time

        except ExtractionError:
            raise
        except AIServiceError as e:
            original = (e.details or {}).get("original_error", str(e))
            remediation = gemini_remediation_hint(
                original,
                settings.GEMINI_RESUME_MODEL,
                config_key=_RESUME_MODEL_CONFIG_KEY,
            )
            logger.error(
                "Resume extraction Gemini failure: filename=%s model=%s %s "
                "gemini_error=%s remediation=%s",
                filename,
                settings.GEMINI_RESUME_MODEL,
                gemini_auth_log_label(settings),
                original,
                remediation,
            )
            raise ExtractionError(
                message="Failed to extract data from resume",
                source="resume",
                details={
                    "filename": filename,
                    "model": settings.GEMINI_RESUME_MODEL,
                    "auth": gemini_auth_log_label(settings),
                    "gemini_error": original,
                    "remediation": remediation,
                },
            ) from e
        except Exception as e:
            logger.error(
                "Failed to extract from %s (model=%s %s): %s",
                filename,
                settings.GEMINI_RESUME_MODEL,
                gemini_auth_log_label(settings),
                e,
                exc_info=True,
            )
            raise ExtractionError(
                message="Failed to extract data from resume",
                source="resume",
                details={
                    "filename": filename,
                    "model": settings.GEMINI_RESUME_MODEL,
                    "auth": gemini_auth_log_label(settings),
                    "error": str(e),
                },
            ) from e

    async def extract_from_text(
        self,
        text_content: str,
    ) -> tuple[ResumeExtractedData, float]:
        """
        Extract structured data from plain text resume content.
        
        Useful for copy-pasted resume text or OCR results.
        
        Args:
            text_content: Plain text resume content
            
        Returns:
            Tuple of (extracted_data, processing_time_ms)
        """
        start_time = time.time()

        settings = get_settings()
        logger.info(
            "Extracting from text (%d chars) model=%s",
            len(text_content),
            settings.GEMINI_RESUME_MODEL,
        )

        try:
            extraction_prompt = self._get_extraction_prompt()
            full_prompt = f"{extraction_prompt}\n\n---\n\nRESUME TEXT:\n{text_content}"

            parsed_data = await self.gemini.generate_structured(
                prompt=full_prompt,
                temperature=0.1,
                max_tokens=settings.GEMINI_RESUME_MAX_TOKENS,
                model=settings.GEMINI_RESUME_MODEL,
                config_key=_RESUME_MODEL_CONFIG_KEY,
                json_mode=True,
            )

            extracted_data = ResumeExtractedData(**parsed_data)
            processing_time = (time.time() - start_time) * 1000

            logger.info("Text extraction completed in %.2fms", processing_time)

            return extracted_data, processing_time

        except ExtractionError:
            raise
        except AIServiceError as e:
            original = (e.details or {}).get("original_error", str(e))
            remediation = gemini_remediation_hint(
                original,
                settings.GEMINI_RESUME_MODEL,
                config_key=_RESUME_MODEL_CONFIG_KEY,
            )
            logger.error(
                "Resume text extraction Gemini failure: model=%s %s "
                "gemini_error=%s remediation=%s",
                settings.GEMINI_RESUME_MODEL,
                gemini_auth_log_label(settings),
                original,
                remediation,
            )
            raise ExtractionError(
                message="Failed to extract data from text",
                source="text",
                details={
                    "model": settings.GEMINI_RESUME_MODEL,
                    "auth": gemini_auth_log_label(settings),
                    "gemini_error": original,
                    "remediation": remediation,
                },
            ) from e
        except Exception as e:
            logger.error("Text extraction failed: %s", e, exc_info=True)
            raise ExtractionError(
                message="Failed to extract data from text",
                source="text",
                details={"error": str(e)},
            ) from e


# Singleton instance
_extraction_service: ResumeExtractionService | None = None


def get_extraction_service() -> ResumeExtractionService:
    """Get the global extraction service instance."""
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = ResumeExtractionService()
    return _extraction_service
