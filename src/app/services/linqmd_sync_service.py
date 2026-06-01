"""
LinQMD Sync Service.

Production-grade service for syncing doctor profiles to the LinQMD platform.
Handles data transformation, file uploads, and error handling.

Features:
- Configurable endpoints (dev/prod)
- Automatic retry with exponential backoff
- Comprehensive error handling and logging
- Data transformation from internal schema to LinQMD format
"""
from __future__ import annotations

import logging
import re
import secrets
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from ..core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class LinQMDUserPayload:
    """Data structure for LinQMD user creation API payload."""
    
    # Required fields
    name: str  # Username for login
    mail: str  # Email address
    password: str  # User password
    fullname: str  # Display name
    phone_number: str
    
    # Professional info
    degree: str = ""  # Qualification/degree
    speciality: str = ""  # Primary specialization
    overview: str = ""  # Professional overview
    specialities_long: str = ""  # Detailed specialities
    expertise_summary: str = ""  # Summary of expertise
    education_details: str = ""  # Education details
    yearsofexperiences: str = ""  # years_post_specialisation, else years_of_clinical_experience
    awards_honors: str = ""  # awards_academic_honours when present
    
    # Arrays of expertise items
    expertises: list[dict[str, str]] = field(default_factory=list)
    
    # YouTube videos
    youtube_videos: list[dict[str, str]] = field(default_factory=list)
    
    # Profile photo file for LinQMD multipart upload: (filename, bytes, content_type)
    display_picture_file: tuple[str, bytes, str] | None = None

    # Practice hub theme (dp_1 | dp_2)
    theme: str = "dp_1"
    
    def to_form_data(self, *, include_theme: bool = True) -> dict[str, str]:
        """
        Build text fields for LinQMD user create/update (multipart when a photo is attached).

        Create: mandatory name, mail, pass, theme
        Update: mandatory name, mail, pass (theme omitted — set only at profile creation)

        displayPicture is sent separately as a file upload, not in this dict.
        """
        payload: dict[str, str] = {
            'name': self.name,
            'mail': self.mail,
            'pass': self.password,
        }
        if include_theme:
            payload['theme'] = self.theme
        
        # Optional fields - only include if they have values
        optional_fields = {
            'fullname': self.fullname,
            'phone_number': self.phone_number,
            'degree': self.degree,
            'speciality': self.speciality,
            'overview': self.overview,
            'specialities_long': self.specialities_long,
            'expertise_summary': self.expertise_summary,
            'education_details': self.education_details,
            'yearsofexperiences': self.yearsofexperiences,
            'awards_honors': self.awards_honors,
        }
        
        # Add non-empty optional fields
        for key, value in optional_fields.items():
            if value:
                payload[key] = value
        
        return payload


@dataclass
class LinQMDSyncResult:
    """Result of a LinQMD sync operation."""
    
    success: bool
    doctor_id: int
    linqmd_response: dict[str, Any] | None = None
    error_message: str | None = None
    http_status_code: int | None = None


class LinQMDSyncService:
    """
    Service for syncing doctor data to LinQMD platform.
    
    Transforms internal doctor data format to LinQMD API format
    and handles the HTTP communication with proper error handling.
    
    Usage:
        service = get_linqmd_sync_service()
        result = await service.sync_doctor(doctor_identity, doctor_details)
    """
    
    def __init__(self) -> None:
        """Initialize the sync service with configuration."""
        self.settings = get_settings()
        self._client: httpx.AsyncClient | None = None
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.settings.LINQMD_API_TIMEOUT,
                follow_redirects=True,
            )
        return self._client
    
    def _get_headers(self) -> dict[str, str]:
        """Build request headers for LinQMD API (Content-Type set by httpx for multipart)."""
        headers: dict[str, str] = {}

        # Auth token already includes "Basic " prefix from config
        if self.settings.LINQMD_PRACTICE_HUB_AUTH_TOKEN:
            headers['Authorization'] = self.settings.LINQMD_PRACTICE_HUB_AUTH_TOKEN
        
        if self.settings.LINQMD_PRACTICE_HUB_COOKIE:
            headers['Cookie'] = self.settings.LINQMD_PRACTICE_HUB_COOKIE
        
        return headers
    

    @staticmethod
    def _slug_field_segment(value: str) -> str:
        """Lowercase alphanumeric slug for a single field (speciality or location)."""
        return ''.join(c.lower() for c in (value or '').strip() if c.isalnum())

    # When normalized speciality exceeds this length, trim trailing words (not mid-word).
    _SPECIALITY_TRUNCATE_TRIGGER_CHARS = 15

    @classmethod
    def _normalize_speciality_text(cls, value: str) -> str:
        """Replace non-alphanumeric characters with spaces and collapse whitespace."""
        text = re.sub(r'[^0-9A-Za-z]+', ' ', (value or '').strip())
        return ' '.join(text.split())

    @classmethod
    def _truncate_speciality_text(cls, text: str) -> str:
        """
        If text exceeds the trigger length, drop trailing words (never mid-word).

        Keeps at least two leading words when possible so titles like
        "Consultant Pediatrician …" are preserved; a single long word is kept whole.
        """
        if len(text) <= cls._SPECIALITY_TRUNCATE_TRIGGER_CHARS:
            return text
        words = text.split()
        while len(words) > 2:
            words.pop()
        return ' '.join(words)

    @classmethod
    def _speciality_username_slug(cls, speciality: str) -> str:
        """
        Prepare speciality for the username slug: normalize, word-boundary truncate, slugify.

        Example: "Consultant Pediatrician & allergy asthma specialist"
        -> "Consultant Pediatrician allergy asthma specialist" (normalized)
        -> "Consultant Pediatrician" (trim trailing words) -> ``consultantpediatrician``.
        """
        normalized = cls._normalize_speciality_text(speciality)
        if not normalized:
            return ''
        truncated = cls._truncate_speciality_text(normalized)
        return cls._slug_field_segment(truncated)

    _HONORIFIC_PREFIXES = frozenset({'dr', 'mr', 'mrs', 'ms', 'prof'})

    @classmethod
    def _slug_name_word_segments(cls, full_name: str) -> list[str]:
        """
        Split full name into hyphen-joined word segments.

        Honorifics (e.g. Dr) are merged with the following word:
        "Dr Murali Mohan Selvam" -> drmurali, mohan, selvam
        """
        raw_words = (full_name or '').split()
        segments: list[str] = []
        i = 0
        while i < len(raw_words):
            segment = ''.join(c.lower() for c in raw_words[i] if c.isalnum())
            if not segment:
                i += 1
                continue

            if (
                segment in cls._HONORIFIC_PREFIXES
                and i + 1 < len(raw_words)
            ):
                next_segment = ''.join(
                    c.lower() for c in raw_words[i + 1] if c.isalnum()
                )
                if next_segment:
                    segments.append(segment + next_segment)
                    i += 2
                    continue

            segments.append(segment)
            i += 1

        return segments

    def _generate_username(
        self,
        speciality: str,
        primary_location: str,
        full_name: str,
        email: str = '',
    ) -> str:
        """
        Generate LinQMD login username: speciality-primarylocation-drfullname.

        Example: Cardiology, Bangalore, "Dr Murali Mohan Selvam"
        -> cardiology-bangalore-drmurali-mohan-selvam
        """
        parts: list[str] = []

        spec = self._speciality_username_slug(speciality)
        if spec:
            parts.append(spec)

        loc = self._slug_field_segment(primary_location)
        if loc:
            parts.append(loc)

        parts.extend(self._slug_name_word_segments(full_name))

        username = '-'.join(parts)
        if len(username) >= 3:
            return username

        # Fallback when required profile fields are missing
        if email and '@' in email:
            email_username = email.split('@')[0].lower()
            email_username = ''.join(
                c for c in email_username if c.isalnum() or c in '._-'
            )
            if len(email_username) >= 3:
                return email_username

        name_base = ''.join(c.lower() for c in (full_name or '') if c.isalnum())
        suffix = ''.join(secrets.choice(string.digits) for _ in range(4))
        return f"{name_base or 'doctor'}{suffix}"
    
    _LINQMD_TEMP_PASSWORD_SPECIALS = '!#'
    _LINQMD_PASSWORD_ADJECTIVES = (
        'Velvet', 'Crimson', 'Golden', 'Silver', 'Amber', 'Azure', 'Jade', 'Ivory',
        'Noble', 'Royal', 'Bright', 'Crystal', 'Pearl', 'Starlit', 'Radiant', 'Serene',
        'Alpine', 'Coastal', 'Lunar', 'Solar', 'Arctic', 'Floral', 'Mystic', 'Gentle',
        'Quiet', 'Swift', 'Clear', 'Sunset', 'Stellar', 'Opal', 'Satin', 'Copper',
    )
    _LINQMD_PASSWORD_NOUNS = (
        'Horizon', 'Summit', 'Meadow', 'Harbor', 'Canyon', 'Valley', 'Garden', 'Phoenix',
        'Marina', 'Prism', 'Orion', 'Cypress', 'Willow', 'Blossom', 'Cascade', 'Meridian',
        'Zephyr', 'Lotus', 'Echo', 'Nova', 'Comet', 'Ridge', 'Brook', 'Shore', 'Crest',
        'Gate', 'Bloom', 'Spark', 'Atlas', 'Falcon', 'Harbour', 'Aurora', 'Ember',
    )

    def _generate_password(self) -> str:
        """
        Generate a temporary LinQMD password.

        Format: {Adjective}{Noun}{digits}{special}
        Example: VelvetHorizon742!

        The word pair is randomized from memorable, name-like tokens (PascalCase).
        Special character is randomized from ! or # only.
        """
        prefix = (
            f'{secrets.choice(self._LINQMD_PASSWORD_ADJECTIVES)}'
            f'{secrets.choice(self._LINQMD_PASSWORD_NOUNS)}'
        )
        digits = ''.join(secrets.choice(string.digits) for _ in range(3))
        special = secrets.choice(self._LINQMD_TEMP_PASSWORD_SPECIALS)
        return f'{prefix}{digits}{special}'

    @staticmethod
    def _stored_uri_to_s3_key(stored_uri: str) -> str | None:
        """Extract S3 object key from a full S3 URL or bare key stored in the DB."""
        stored_uri = (stored_uri or "").strip()
        if not stored_uri:
            return None
        if ".amazonaws.com/" in stored_uri:
            return stored_uri.split(".amazonaws.com/", 1)[1].split("?", 1)[0]
        if not stored_uri.startswith("http"):
            return stored_uri.split("?", 1)[0]
        return None

    @staticmethod
    def _parse_local_profile_photo_uri(stored_uri: str) -> tuple[str, int, str] | None:
        """Parse local blob URI into (blob_id, doctor_id, extension)."""
        match = re.search(r"/(\d+)/profile_photo/([^/?#]+)$", stored_uri)
        if not match:
            return None
        doctor_id = int(match.group(1))
        filename = match.group(2)
        extension = Path(filename).suffix or ".jpg"
        blob_id = Path(filename).stem
        return blob_id, doctor_id, extension

    async def _load_display_picture_file(
        self,
        profile_photo: str | None,
        media: list[dict[str, Any]] | None = None,
    ) -> tuple[str, bytes, str] | None:
        """
        Load doctor profile photo bytes for LinQMD multipart upload.

        Uses doctors.profile_photo (S3 key or URL). Falls back to doctor_media
        with category profile_photo when the column is empty.
        """
        stored = (profile_photo or "").strip()
        if not stored and media:
            for item in media:
                if item.get("media_category") == "profile_photo" and item.get("file_uri"):
                    stored = str(item["file_uri"]).strip()
                    break
        if not stored:
            logger.info("LinQMD displayPicture: no profile photo on record")
            return None

        from .blob_storage_service import (
            LocalBlobStorageService,
            S3BlobStorageService,
            get_blob_storage_service,
        )

        blob_service = get_blob_storage_service()

        if isinstance(blob_service, S3BlobStorageService):
            s3_key = self._stored_uri_to_s3_key(stored)
            if s3_key:
                try:
                    content, filename, content_type = await blob_service.get_object_bytes(
                        s3_key
                    )
                    logger.info(
                        "LinQMD displayPicture: loaded from S3 key=%s bytes=%d",
                        s3_key,
                        len(content),
                    )
                    return filename, content, content_type
                except Exception as exc:
                    logger.warning(
                        "LinQMD displayPicture: S3 get_object failed for key=%s: %s",
                        s3_key,
                        exc,
                    )

        if isinstance(blob_service, LocalBlobStorageService):
            parsed = self._parse_local_profile_photo_uri(stored)
            if parsed:
                blob_id, doc_id, extension = parsed
                try:
                    content, meta = await blob_service.get_blob(
                        blob_id, doc_id, "profile_photo", extension
                    )
                    filename = meta.file_name or f"profile_photo{extension}"
                    logger.info(
                        "LinQMD displayPicture: loaded from local storage doctor_id=%s bytes=%d",
                        doc_id,
                        len(content),
                    )
                    return filename, content, meta.mime_type
                except Exception as exc:
                    logger.warning(
                        "LinQMD displayPicture: local blob read failed: %s", exc
                    )

        download_url = stored
        if stored.startswith("/"):
            base = (self.settings.BLOB_BASE_URL or "").rstrip("/")
            if base.startswith("http"):
                download_url = f"{base}{stored}"
            else:
                logger.warning(
                    "LinQMD displayPicture: relative URI without HTTP BLOB_BASE_URL: %s",
                    stored,
                )
                return None

        if download_url.startswith("http"):
            try:
                content, suggested = await blob_service._download_from_url(download_url)
                filename = suggested or "profile_photo.jpg"
                content_type = blob_service._detect_mime_type(filename, content)
                logger.info(
                    "LinQMD displayPicture: downloaded from URL bytes=%d",
                    len(content),
                )
                return filename, content, content_type
            except Exception as exc:
                logger.warning(
                    "LinQMD displayPicture: HTTP download failed for %s: %s",
                    download_url,
                    exc,
                )

        logger.warning(
            "LinQMD displayPicture: could not resolve profile photo: %s",
            stored[:120],
        )
        return None
    
    def transform_doctor_data(
        self,
        identity: dict[str, Any],
        details: dict[str, Any] | None = None,
        media: list[dict[str, Any]] | None = None,
        *,
        linqmd_username: str | None = None,
        linqmd_password: str | None = None,
        include_theme: bool = True,
    ) -> LinQMDUserPayload:
        """
        Transform internal doctor data to LinQMD API format.
        
        Args:
            identity: Doctor identity data (from doctor_identity table)
            details: Doctor details data (from doctor_details table)
            media: Doctor media files (from doctor_media table)
            
        Returns:
            LinQMDUserPayload ready for API submission
        """
        details = details or {}
        media = media or []
        
        # Get full name
        fullname = identity.get('full_name', '').strip()

        speciality = (
            details.get('speciality', '')
            or details.get('specialty', '')
            or identity.get('speciality', '')
            or identity.get('specialty', '')
            or ''
        )
        primary_location = (
            details.get('primary_practice_location', '')
            or details.get('primary_location', '')
            or identity.get('primary_practice_location', '')
            or ''
        )

        username = linqmd_username or self._generate_username(
            speciality,
            primary_location,
            fullname,
            identity.get('email', ''),
        )

        # Format qualifications as degree string
        qualifications = details.get('qualifications', []) or []
        degree_parts = []
        for qual in qualifications:
            if isinstance(qual, dict):
                deg = qual.get('degree', '')
                if deg:
                    degree_parts.append(deg)
            elif isinstance(qual, str):
                degree_parts.append(qual)
        degree = ', '.join(degree_parts) if degree_parts else ''
        
        # Format education details
        education_lines = []
        for qual in qualifications:
            if isinstance(qual, dict):
                deg = qual.get('degree', '')
                inst = qual.get('institution', '')
                year = qual.get('year', '')
                if deg:
                    line = deg
                    if inst:
                        line += f" - {inst}"
                    if year:
                        line += f" ({year})"
                    education_lines.append(line)
            elif isinstance(qual, str):
                education_lines.append(qual)
        education_details = '\n'.join(education_lines)
        
        # Format specialities (speciality resolved above for username)
        if not speciality:
            speciality = details.get('speciality', '') or ''
        sub_specialities = details.get('sub_specialities', []) or []
        specialities_long = ', '.join([speciality] + sub_specialities) if sub_specialities else speciality
        
        # Build expertises array from areas_of_expertise
        expertises = []
        areas = details.get('areas_of_expertise', []) or []
        for area in areas:
            if isinstance(area, str) and area:
                expertises.append({
                    'head': area,
                    'content': f"Expert in {area}"  # Basic content
                })
        
        # Add conditions treated as expertises
        conditions = details.get('conditions_treated', []) or []
        for condition in conditions[:5]:  # Limit to 5
            if isinstance(condition, str) and condition:
                expertises.append({
                    'head': f"Treatment: {condition}",
                    'content': f"Specialized treatment for {condition}"
                })
        
        # Build expertise summary
        procedures = details.get('procedures_performed', []) or []
        expertise_parts = []
        if areas:
            expertise_parts.append(f"Areas of Expertise: {', '.join(areas[:5])}")
        if procedures:
            expertise_parts.append(f"Procedures: {', '.join(procedures[:5])}")
        expertise_summary = '\n'.join(expertise_parts)
        
        # Get overview/about text
        overview = details.get('professional_overview', '') or details.get('about_me', '') or ''

        years_value = details.get('years_post_specialisation')
        if years_value is None:
            years_value = details.get('years_of_clinical_experience')
        yearsofexperiences = (
            str(years_value) if years_value is not None else ''
        )

        awards_raw = details.get('awards_academic_honours', []) or []
        awards_parts: list[str] = []
        for item in awards_raw:
            if isinstance(item, str) and item.strip():
                awards_parts.append(item.strip())
            elif isinstance(item, dict):
                label = (
                    item.get('title')
                    or item.get('name')
                    or item.get('award')
                    or ''
                )
                if str(label).strip():
                    awards_parts.append(str(label).strip())
        awards_honors = ', '.join(awards_parts)
        
        password = linqmd_password or self._generate_password()
        theme = secrets.choice(('dp_1', 'dp_2')) if include_theme else 'dp_1'

        return LinQMDUserPayload(
            name=username,
            mail=identity.get('email', ''),
            password=password,
            fullname=fullname,
            phone_number=identity.get('phone_number', ''),
            theme=theme,
            degree=degree,
            speciality=speciality,
            overview=overview,
            specialities_long=specialities_long,
            expertise_summary=expertise_summary,
            education_details=education_details,
            yearsofexperiences=yearsofexperiences,
            awards_honors=awards_honors,
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _post_user_multipart(
        self,
        url: str,
        payload: LinQMDUserPayload,
        *,
        include_theme: bool,
        attach_credentials_to_response: bool,
    ) -> tuple[int, dict[str, Any]]:
        """POST multipart user payload to a LinQMD user create or update URL."""
        form_data = payload.to_form_data(include_theme=include_theme)
        headers = self._get_headers()

        files: dict[str, tuple[str, bytes, str]] | None = None
        if payload.display_picture_file:
            filename, content, content_type = payload.display_picture_file
            files = {
                'displayPicture': (filename, content, content_type),
            }

        safe_log_data = {k: v for k, v in form_data.items() if k != 'pass'}
        logger.info(
            "LinQMD user request: url=%s mail=%s has_display_picture=%s include_theme=%s",
            url,
            payload.mail,
            files is not None,
            include_theme,
        )
        logger.debug(
            "LinQMD fields=%s display_picture_bytes=%s",
            safe_log_data,
            len(payload.display_picture_file[1])
            if payload.display_picture_file
            else 0,
        )

        if files:
            response = await self.client.post(
                url,
                data=form_data,
                files=files,
                headers=headers,
            )
        else:
            response = await self.client.post(
                url,
                data=form_data,
                headers=headers,
            )

        logger.info("LinQMD response: status=%s url=%s", response.status_code, url)

        try:
            response_json = response.json()
        except Exception:
            response_json = {"raw_response": response.text[:500]}

        if isinstance(response_json, dict):
            response_json = dict(response_json)
        else:
            response_json = {"raw_response": response_json}

        if attach_credentials_to_response:
            response_json["Username"] = payload.name
            response_json["Password"] = payload.password

        return response.status_code, response_json

    async def _send_to_linqmd(
        self,
        payload: LinQMDUserPayload,
    ) -> tuple[int, dict[str, Any]]:
        """Send user data to LinQMD user create API with retry logic."""
        return await self._post_user_multipart(
            self.settings.linqmd_user_create_url,
            payload,
            include_theme=True,
            attach_credentials_to_response=True,
        )

    def _finalize_sync_result(
        self,
        doctor_id: int,
        status_code: int,
        response_json: dict[str, Any],
    ) -> LinQMDSyncResult:
        """Map LinQMD HTTP response to LinQMDSyncResult."""
        success = 200 <= status_code < 300
        api_error = (
            response_json.get("error")
            if isinstance(response_json, dict)
            else None
        )
        if success and api_error:
            success = False

        error_message: str | None = None
        if not success:
            if api_error:
                error_message = str(api_error)
            elif isinstance(response_json, dict) and response_json.get("message"):
                error_message = str(response_json["message"])
            else:
                error_message = f"API returned status {status_code}"

        return LinQMDSyncResult(
            success=success,
            doctor_id=doctor_id,
            linqmd_response=response_json,
            http_status_code=status_code,
            error_message=error_message,
        )

    async def _build_sync_context(
        self,
        doctor_id: int,
        db_session: Any,
    ) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]] | None:
        """Load identity, doctor row, and media for LinQMD sync. None if identity missing."""
        from ..repositories.onboarding_repository import OnboardingRepository

        repo = OnboardingRepository(db_session)
        identity = await repo.get_identity_by_doctor_id(doctor_id)
        if not identity:
            return None

        from ..repositories.doctor_repository import DoctorRepository

        doc_repo = DoctorRepository(db_session)
        details = await doc_repo.get_by_id(doctor_id)
        media = await repo.list_media(doctor_id)

        identity_dict = {
            'doctor_id': identity.doctor_id,
            'full_name': identity.full_name,
            'email': identity.email,
            'phone_number': identity.phone_number,
            'profile_photo': getattr(details, 'profile_photo', None) if details else None,
        }

        details_dict = None
        if details:
            details_dict = {
                'gender': getattr(details, 'gender', None),
                'speciality': getattr(
                    details,
                    'specialty',
                    getattr(details, 'speciality', getattr(details, 'primary_specialization', None)),
                ),
                'primary_practice_location': getattr(details, 'primary_practice_location', None),
                'sub_specialities': getattr(details, 'sub_specialities', []),
                'areas_of_expertise': getattr(details, 'areas_of_clinical_interest', []),
                'qualifications': getattr(details, 'qualifications', []),
                'professional_overview': getattr(
                    details,
                    'professional_overview',
                    getattr(details, 'professional_achievement', None),
                ),
                'about_me': getattr(
                    details,
                    'about_me',
                    getattr(details, 'personal_achievement', None),
                ),
                'conditions_treated': getattr(details, 'conditions_treated', []),
                'procedures_performed': getattr(details, 'procedures_performed', []),
                'external_links': getattr(details, 'external_links', {}),
                'years_post_specialisation': getattr(
                    details, 'years_post_specialisation', None
                ),
                'years_of_clinical_experience': getattr(
                    details, 'years_of_clinical_experience', None
                ),
                'awards_academic_honours': getattr(
                    details, 'awards_academic_honours', []
                ),
            }

        media_list = [
            {
                'media_category': m.media_category,
                'file_uri': m.file_uri,
                'is_primary': m.is_primary,
            }
            for m in media
        ]
        return identity_dict, details_dict, media_list

    async def sync_doctor(
        self,
        identity: dict[str, Any],
        details: dict[str, Any] | None = None,
        media: list[dict[str, Any]] | None = None,
        doctor_id: int | None = None,
    ) -> LinQMDSyncResult:
        """
        Sync a doctor's data to LinQMD platform.
        
        Args:
            identity: Doctor identity data
            details: Doctor details data (optional)
            media: Doctor media files (optional)
            doctor_id: Internal doctor ID for tracking
            
        Returns:
            LinQMDSyncResult with success status and details
        """
        doctor_id = doctor_id or identity.get('doctor_id', 0)
        
        try:
            display_picture_file = await self._load_display_picture_file(
                identity.get('profile_photo'),
                media,
            )

            # Transform data to LinQMD format
            payload = self.transform_doctor_data(identity, details, media)
            payload.display_picture_file = display_picture_file
            
            status_code, response_json = await self._send_to_linqmd(payload)
            result = self._finalize_sync_result(doctor_id, status_code, response_json)
            if result.success:
                logger.info("Successfully created/synced doctor %s on LinQMD", doctor_id)
            else:
                logger.error(
                    "Failed to sync doctor %s to LinQMD: %s",
                    doctor_id,
                    response_json,
                )
            return result
            
        except httpx.TimeoutException as e:
            logger.error(f"Timeout syncing doctor {doctor_id} to LinQMD: {e}")
            return LinQMDSyncResult(
                success=False,
                doctor_id=doctor_id,
                error_message=f"Request timeout: {e}",
            )
        except httpx.ConnectError as e:
            logger.error(f"Connection error syncing doctor {doctor_id} to LinQMD: {e}")
            return LinQMDSyncResult(
                success=False,
                doctor_id=doctor_id,
                error_message=f"Connection error: {e}",
            )
        except Exception as e:
            logger.exception(f"Unexpected error syncing doctor {doctor_id} to LinQMD")
            return LinQMDSyncResult(
                success=False,
                doctor_id=doctor_id,
                error_message=f"Unexpected error: {str(e)}",
            )
    
    async def sync_doctor_by_id(
        self,
        doctor_id: int,
        db_session: Any,
    ) -> LinQMDSyncResult:
        """
        Create a LinQMD user by internal doctor ID (admin initial profile creation).
        """
        context = await self._build_sync_context(doctor_id, db_session)
        if context is None:
            return LinQMDSyncResult(
                success=False,
                doctor_id=doctor_id,
                error_message=f"Doctor with ID {doctor_id} not found",
            )
        identity_dict, details_dict, media_list = context
        return await self.sync_doctor(identity_dict, details_dict, media_list, doctor_id)

    async def _send_update_to_linqmd(
        self,
        linqmd_user_id: str,
        payload: LinQMDUserPayload,
    ) -> tuple[int, dict[str, Any]]:
        """Send user data to LinQMD user update API (no theme field)."""
        update_url = self.settings.linqmd_user_update_url(linqmd_user_id)
        return await self._post_user_multipart(
            update_url,
            payload,
            include_theme=False,
            attach_credentials_to_response=False,
        )

    async def sync_doctor_update_by_id(
        self,
        doctor_id: int,
        db_session: Any,
    ) -> LinQMDSyncResult:
        """
        Push current Caepy profile data to LinQMD when credentials already exist.

        No-op (success) when doctor_linqmd_credentials row is missing.
        """
        from ..repositories.linqmd_credentials_repository import LinqmdCredentialsRepository

        creds_repo = LinqmdCredentialsRepository(db_session)
        creds = await creds_repo.get_by_doctor_id(doctor_id)
        if creds is None:
            return LinQMDSyncResult(
                success=True,
                doctor_id=doctor_id,
                linqmd_response={"skipped": "no_linqmd_credentials"},
            )

        context = await self._build_sync_context(doctor_id, db_session)
        if context is None:
            return LinQMDSyncResult(
                success=False,
                doctor_id=doctor_id,
                error_message=f"Doctor with ID {doctor_id} not found",
            )

        identity_dict, details_dict, media_list = context
        doctor_id = doctor_id or identity_dict.get('doctor_id', 0)

        try:
            display_picture_file = await self._load_display_picture_file(
                identity_dict.get('profile_photo'),
                media_list,
            )
            payload = self.transform_doctor_data(
                identity_dict,
                details_dict,
                media_list,
                linqmd_username=creds.linqmd_username,
                linqmd_password=creds.linqmd_password,
                include_theme=False,
            )
            payload.display_picture_file = display_picture_file

            status_code, response_json = await self._send_update_to_linqmd(
                creds.linqmd_user_id,
                payload,
            )
            result = self._finalize_sync_result(doctor_id, status_code, response_json)
            if result.success:
                logger.info(
                    "LinQMD profile updated doctor_id=%s linqmd_user_id=%s",
                    doctor_id,
                    creds.linqmd_user_id,
                )
            else:
                logger.warning(
                    "LinQMD profile update failed doctor_id=%s: %s",
                    doctor_id,
                    response_json,
                )
            return result

        except httpx.TimeoutException as e:
            logger.error("Timeout updating LinQMD profile doctor_id=%s: %s", doctor_id, e)
            return LinQMDSyncResult(
                success=False,
                doctor_id=doctor_id,
                error_message=f"Request timeout: {e}",
            )
        except httpx.ConnectError as e:
            logger.error("Connection error updating LinQMD profile doctor_id=%s: %s", doctor_id, e)
            return LinQMDSyncResult(
                success=False,
                doctor_id=doctor_id,
                error_message=f"Connection error: {e}",
            )
        except Exception as e:
            logger.exception("Unexpected error updating LinQMD profile doctor_id=%s", doctor_id)
            return LinQMDSyncResult(
                success=False,
                doctor_id=doctor_id,
                error_message=f"Unexpected error: {str(e)}",
            )


# -----------------------------------------------------------------------------
# Singleton Pattern
# -----------------------------------------------------------------------------

_linqmd_sync_service: LinQMDSyncService | None = None


def get_linqmd_sync_service() -> LinQMDSyncService:
    """Get the global LinQMD sync service instance."""
    global _linqmd_sync_service
    if _linqmd_sync_service is None:
        _linqmd_sync_service = LinQMDSyncService()
    return _linqmd_sync_service


async def sync_linqmd_profile_update_if_credentials_exist(
    doctor_id: int,
    db_session: Any,
) -> None:
    """Best-effort LinQMD profile update after a Caepy doctor profile change.

    Does nothing when ``doctor_linqmd_credentials`` has no row for the doctor.
    Failures are logged only so the caller's HTTP response is not blocked.
    """
    try:
        result = await get_linqmd_sync_service().sync_doctor_update_by_id(
            doctor_id,
            db_session,
        )
        if not result.success and result.error_message:
            logger.warning(
                "LinQMD profile update failed doctor_id=%s: %s",
                doctor_id,
                result.error_message,
            )
    except Exception:
        logger.exception(
            "LinQMD profile update error doctor_id=%s",
            doctor_id,
        )