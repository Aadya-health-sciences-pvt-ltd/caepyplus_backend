"""
LinQMD Practice Hub service for blog publishing.

Handles Caepy login and multipart blog creation against the Practice Hub API.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from ..core.config import get_settings

logger = logging.getLogger(__name__)


class LinqmdLoginError(Exception):
    """Practice Hub login failed (invalid credentials or API error)."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        *,
        code: str = "linqmd_credentials_invalid",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class LinqmdPublishError(Exception):
    """Practice Hub blog publish failed."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class PracticeHubLoginResult:
    access_token: str
    refresh_token: str | None
    raw_response: dict[str, Any]


@dataclass
class PracticeHubBlogPayload:
    title: str
    subtitle: str | None
    content: str | None
    image_bytes: bytes | None = None
    image_filename: str | None = None
    image_content_type: str | None = None
    image_alt: str | None = None


def build_field_blog_title(title: str, max_len: int = 50) -> str:
    """Letters and spaces only; truncate at last full word within max_len."""
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", "", title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return "Blog"
    if len(cleaned) <= max_len:
        return cleaned
    truncated = cleaned[:max_len]
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated.strip() or "Blog"


def build_blog_title_slug(title: str, max_len: int = 80) -> str:
    """SEO-friendly URL slug for Practice Hub ``Title`` (lowercase, hyphen-separated)."""
    text = re.sub(r"[^0-9A-Za-z]+", " ", (title or "").strip())
    words = [w.lower() for w in text.split() if w]
    if not words:
        return "blog"
    slug = "-".join(words)
    if len(slug) <= max_len:
        return slug
    truncated = slug[:max_len].rstrip("-")
    if "-" in truncated:
        truncated = truncated.rsplit("-", 1)[0]
    return truncated or "blog"


def build_blog_live_url(*, base_url: str, username: str, title: str) -> str:
    """Public LinQMD blog URL: slug of ``build_field_blog_title(title)``."""
    base = (base_url or "").rstrip("/")
    user = (username or "").strip().lstrip("/")
    field_title = build_field_blog_title(title)
    slug = build_blog_title_slug(field_title)
    return f"{base}/doctor/{user}/blog/{slug}"


def resolve_blog_live_url(
    *,
    blog_status: str | None,
    title: str | None,
    linqmd_username: str | None,
    base_url: str,
    seo_schema_markup: dict[str, Any] | None = None,
) -> str | None:
    """Compute live blog URL for published posts (not persisted)."""
    if (blog_status or "").lower() != "published":
        return None
    if isinstance(seo_schema_markup, dict):
        stored = seo_schema_markup.get("live_url")
        if isinstance(stored, str) and stored.strip():
            return stored.strip()
    if not linqmd_username or not (title or "").strip():
        return None
    return build_blog_live_url(
        base_url=base_url,
        username=linqmd_username,
        title=title or "",
    )


def extract_image_alt_from_html(content: str | None) -> str | None:
    """Return alt text from the first img tag in HTML content."""
    if not content:
        return None
    match = re.search(r'<img[^>]+alt=["\']([^"\']*)["\']', content, re.IGNORECASE)
    if match:
        alt = match.group(1).strip()
        return alt if alt else None
    return None


def _stored_uri_to_s3_key(stored_uri: str) -> str | None:
    stored_uri = (stored_uri or "").strip()
    if not stored_uri:
        return None
    if ".amazonaws.com/" in stored_uri:
        return stored_uri.split(".amazonaws.com/", 1)[1].split("?", 1)[0]
    if not stored_uri.startswith("http"):
        return stored_uri.split("?", 1)[0]
    return None


def parse_practice_hub_login_tokens(body: dict[str, Any]) -> tuple[str | None, str | None]:
    """Extract tokens from Practice Hub login JSON (flat or ``data`` wrapper)."""
    access_token = body.get("access_token")
    refresh_token = body.get("refresh_token")

    nested = body.get("data")
    if isinstance(nested, dict):
        if not access_token:
            access_token = nested.get("access_token")
        if refresh_token is None:
            refresh_token = nested.get("refresh_token")

    if not isinstance(access_token, str) or not access_token.strip():
        return None, None
    if refresh_token is not None and not isinstance(refresh_token, str):
        refresh_token = None
    elif isinstance(refresh_token, str) and not refresh_token.strip():
        refresh_token = None

    return access_token.strip(), refresh_token


def _practice_hub_error_message(body: dict[str, Any], fallback: str) -> str:
    for key in ("error", "message", "msg"):
        val = body.get(key)
        if val:
            return str(val)
    nested = body.get("data")
    if isinstance(nested, dict):
        for key in ("error", "message", "msg"):
            val = nested.get(key)
            if val:
                return str(val)
    return fallback


class LinqmdPracticeHubService:
    """Client for Practice Hub login and blog publish."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.settings.LINQMD_API_TIMEOUT,
                follow_redirects=True,
            )
        return self._client

    async def login(self, username: str, password: str) -> PracticeHubLoginResult:
        """POST JSON credentials to Practice Hub Caepy login."""
        url = self.settings.linqmd_login_url
        payload = {"username": username, "password": password}
        logger.info("Practice Hub login attempt for username=%s", username)

        try:
            response = await self.client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        except httpx.TimeoutException as exc:
            raise LinqmdLoginError(f"Practice Hub login timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise LinqmdLoginError(f"Practice Hub login connection error: {exc}") from exc

        try:
            body: dict[str, Any] = response.json() if response.content else {}
        except Exception:
            body = {"raw_response": response.text[:500]}

        if response.status_code != 200:
            detail = _practice_hub_error_message(body, response.text[:200])
            logger.warning(
                "Practice Hub login HTTP error status=%s url=%s body_keys=%s",
                response.status_code,
                url,
                sorted(body.keys()) if isinstance(body, dict) else [],
            )
            raise LinqmdLoginError(
                f"Practice Hub login failed: {detail}",
                status_code=response.status_code,
            )

        access_token, refresh_token = parse_practice_hub_login_tokens(body)
        if not access_token:
            logger.warning(
                "Practice Hub login missing access_token url=%s status=%s body_keys=%s",
                url,
                response.status_code,
                sorted(body.keys()) if isinstance(body, dict) else [],
            )
            raise LinqmdLoginError(
                "Practice Hub login succeeded but access_token was missing",
                status_code=response.status_code,
                code="linqmd_login_response_invalid",
            )

        logger.info("Practice Hub login successful for username=%s", username)
        return PracticeHubLoginResult(
            access_token=access_token,
            refresh_token=refresh_token,
            raw_response=body,
        )

    def _build_multipart_form(self, blog: PracticeHubBlogPayload) -> dict[str, Any]:
        title = blog.title or "Untitled Blog"
        form: dict[str, Any] = {
            "Title": build_field_blog_title(title),
            "field_blog_title": build_field_blog_title(title),
            "short_description": blog.subtitle or "",
            "body": blog.content or "",
            "category": "1",
            "published": "true",
            "clinic": "",
        }
        if blog.image_alt:
            form["image_alt"] = blog.image_alt
        return form

    async def publish_blog(
        self,
        access_token: str,
        blog: PracticeHubBlogPayload,
    ) -> dict[str, Any]:
        """POST multipart blog to Practice Hub with Bearer token."""
        url = self.settings.linqmd_blogs_url
        headers = {"Authorization": f"Bearer {access_token}"}
        form_data = self._build_multipart_form(blog)

        files: dict[str, tuple[str, bytes, str]] | None = None
        if blog.image_bytes and blog.image_filename:
            content_type = blog.image_content_type or "image/jpeg"
            files = {
                "image": (blog.image_filename, blog.image_bytes, content_type),
            }

        logger.info(
            "Practice Hub blog publish: title=%s has_image=%s",
            blog.title,
            files is not None,
        )

        try:
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
        except httpx.TimeoutException as exc:
            raise LinqmdPublishError(f"Practice Hub publish timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise LinqmdPublishError(
                f"Practice Hub publish connection error: {exc}"
            ) from exc

        try:
            body: dict[str, Any] = response.json() if response.content else {}
        except Exception:
            body = {"raw_response": response.text[:500]}

        if response.status_code < 200 or response.status_code >= 300:
            detail = body.get("error") or body.get("message") or response.text[:200]
            logger.warning(
                "Practice Hub blog publish HTTP error status=%s url=%s detail=%s body_keys=%s",
                response.status_code,
                url,
                str(detail)[:300],
                sorted(body.keys()) if isinstance(body, dict) else [],
            )
            raise LinqmdPublishError(
                f"Practice Hub blog publish failed: {detail}",
                status_code=response.status_code,
            )

        logger.info("Practice Hub blog publish successful status=%s", response.status_code)
        return body

    async def load_blog_image_from_storage(
        self,
        image_uri: str,
    ) -> tuple[bytes, str, str] | None:
        """Download first blog image bytes from S3 key or HTTP URL."""
        stored = (image_uri or "").strip()
        if not stored:
            return None

        from .blob_storage_service import S3BlobStorageService, get_blob_storage_service

        blob_service = get_blob_storage_service()

        if isinstance(blob_service, S3BlobStorageService):
            s3_key = _stored_uri_to_s3_key(stored)
            if s3_key:
                try:
                    return await blob_service.get_object_bytes(s3_key)
                except Exception as exc:
                    logger.warning(
                        "Failed to load blog image from S3 key=%s: %s", s3_key, exc
                    )

        if stored.startswith("http"):
            try:
                content, suggested = await blob_service._download_from_url(stored)
                filename = suggested or "blog_image.jpg"
                content_type = blob_service._detect_mime_type(filename, content)
                return content, filename, content_type
            except Exception as exc:
                logger.warning("Failed to download blog image from URL: %s", exc)

        return None

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


_linqmd_practice_hub_service: LinqmdPracticeHubService | None = None


def get_linqmd_practice_hub_service() -> LinqmdPracticeHubService:
    global _linqmd_practice_hub_service
    if _linqmd_practice_hub_service is None:
        _linqmd_practice_hub_service = LinqmdPracticeHubService()
    return _linqmd_practice_hub_service
