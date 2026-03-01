"""
Email Service.

Async SMTP email delivery using aiosmtplib + stdlib email.mime.
Templates are loaded from config/email_templates.yaml and rendered
with regex-based substitution so CSS braces don't interfere.
Changes to copy take effect immediately without a server restart.

Usage
-----
    from app.services.email_service import EmailService, get_email_service

    # Inside a FastAPI endpoint (via Depends):
    email_svc: EmailService = Depends(get_email_service)
    await email_svc.send_verification_notification(
        to_address="doctor@example.com",
        action="verified",
        template_vars={...},
        subject_override="Custom subject",   # optional – admin-edited
        body_html_override="<p>…</p>",       # optional – admin-edited
    )
"""

from __future__ import annotations

import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Literal

import aiosmtplib
import structlog
import yaml
from fastapi import Depends

from ..core.config import Settings, get_settings

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------

_TEMPLATE_CACHE: dict[str, Any] | None = None


def _load_templates(path: str) -> dict[str, Any]:
    """Load email templates from YAML.  Result is module-level cached so the
    file is only read once per process lifetime (reload by restarting the app
    or calling ``_invalidate_template_cache()`` in tests).
    """
    global _TEMPLATE_CACHE  # noqa: PLW0603
    if _TEMPLATE_CACHE is None:
        resolved = Path(path)
        if not resolved.is_absolute():
            # Resolve relative to the project root (three levels above src/app/services/)
            project_root = Path(__file__).parents[3]
            resolved = project_root / path
        with resolved.open(encoding="utf-8") as fh:
            _TEMPLATE_CACHE = yaml.safe_load(fh) or {}
        log.info("email_templates_loaded", path=str(resolved))
    return _TEMPLATE_CACHE


def _invalidate_template_cache() -> None:
    """Force next call to _load_templates to re-read disk.  Intended for tests."""
    global _TEMPLATE_CACHE  # noqa: PLW0603
    _TEMPLATE_CACHE = None


def get_template(
    action: Literal["verified", "rejected"],
    templates_path: str,
) -> dict[str, str]:
    """Return the raw (un-rendered) subject + body_html + body_text for *action*."""
    all_templates = _load_templates(templates_path)
    tmpl = all_templates.get(action)
    if not tmpl:
        raise ValueError(f"No email template found for action '{action}'")
    return {
        "subject": tmpl.get("subject", ""),
        "body_html": tmpl.get("body_html", ""),
        "body_text": tmpl.get("body_text", ""),
    }


def render_template(template: dict[str, str], variables: dict[str, str]) -> dict[str, str]:
    """Substitute ``{placeholders}`` in subject/body with *variables*.

    Uses regex to only match {variable_name} patterns (alphanumeric + underscore),
    leaving CSS braces and other syntax untouched. Unknown placeholders are left as-is.
    """
    def replace(text: str) -> str:
        def sub_func(match: re.Match[str]) -> str:
            key = match.group(1)
            return variables.get(key, match.group(0))  # Return original if not found

        # Match {variable_name} where variable_name is alphanumeric + underscore
        return re.sub(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', sub_func, text)

    return {
        "subject": replace(template["subject"]),
        "body_html": replace(template["body_html"]),
        "body_text": replace(template["body_text"]),
    }


# ---------------------------------------------------------------------------
# EmailService
# ---------------------------------------------------------------------------


class EmailService:
    """Async SMTP email service.

    Designed to be instantiated per-request via ``get_email_service()`` so
    settings changes between requests are always picked up.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def build_template_vars(
        self,
        *,
        doctor_name: str,
        first_name: str,
        medical_registration_number: str,
        medical_council: str,
        specialization: str,
        reason: str = "",
        admin_notes: str = "",
    ) -> dict[str, str]:
        """Assemble the standard substitution dictionary for a doctor email."""
        return {
            "doctor_name": doctor_name,
            "first_name": first_name,
            "medical_registration_number": medical_registration_number or "N/A",
            "medical_council": medical_council or "N/A",
            "specialization": specialization or "N/A",
            "reason": reason or "No specific reason provided.",
            "admin_notes": admin_notes or "",
            "platform_name": self._settings.EMAIL_FROM_NAME,
            "support_email": self._settings.EMAIL_FROM_ADDRESS,
        }

    def get_prefilled_template(
        self,
        action: Literal["verified", "rejected"],
        template_vars: dict[str, str],
    ) -> dict[str, str]:
        """Return a rendered (pre-filled) subject + body_html for the frontend popup.

        The frontend can present these to the admin in editable fields.
        """
        raw = get_template(action, self._settings.EMAIL_TEMPLATES_PATH)
        return render_template(raw, template_vars)

    async def send_notification(
        self,
        *,
        to_address: str,
        action: Literal["verified", "rejected"],
        template_vars: dict[str, str],
        subject_override: str | None = None,
        body_html_override: str | None = None,
    ) -> None:
        """Send a verification/rejection email to *to_address*.

        Args:
            to_address:        Recipient email address (doctor's email).
            action:            ``"verified"`` or ``"rejected"``.
            template_vars:     Dict of placeholder values; see ``build_template_vars``.
            subject_override:  If supplied, replaces the template subject (admin-edited).
            body_html_override: If supplied, replaces the template HTML body (admin-edited).

        Raises:
            RuntimeError: If email is disabled in settings.
            aiosmtplib.SMTPException: On SMTP transport errors (caller should catch).
        """
        if not self._settings.EMAIL_ENABLED:
            log.warning(
                "email_skipped_disabled",
                to=to_address,
                action=action,
            )
            raise RuntimeError(
                "Email sending is disabled.  Set EMAIL_ENABLED=true and configure SMTP settings."
            )

        # Render template
        rendered = self.get_prefilled_template(action, template_vars)
        subject = subject_override if subject_override else rendered["subject"]
        body_html = body_html_override if body_html_override else rendered["body_html"]
        body_text = rendered["body_text"]  # plain-text fallback always from template

        # Build MIME message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = (
            f"{self._settings.EMAIL_FROM_NAME} <{self._settings.EMAIL_FROM_ADDRESS}>"
        )
        msg["To"] = to_address

        # Attach plain-text first, HTML second (per RFC 2046 preference order)
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        log.info(
            "email_sending",
            to=to_address,
            action=action,
            subject=subject,
            smtp_host=self._settings.SMTP_HOST,
            smtp_port=self._settings.SMTP_PORT,
        )

        await self._smtp_send(msg)

        log.info("email_sent", to=to_address, action=action)

    # ------------------------------------------------------------------
    # SMTP transport
    # ------------------------------------------------------------------

    async def _smtp_send(self, msg: MIMEMultipart) -> None:
        """Low-level SMTP dispatch.  Handles STARTTLS and implicit-SSL modes."""
        s = self._settings
        kwargs: dict[str, Any] = {
            "hostname": s.SMTP_HOST,
            "port": s.SMTP_PORT,
            "timeout": s.EMAIL_TIMEOUT_SECONDS,
            "use_tls": s.SMTP_USE_SSL,  # True = implicit SSL from handshake (port 465)
        }

        try:
            async with aiosmtplib.SMTP(**kwargs) as smtp:
                if s.SMTP_USE_TLS and not s.SMTP_USE_SSL:
                    # STARTTLS upgrade (port 587)
                    await smtp.starttls()
                if s.SMTP_USERNAME and s.SMTP_PASSWORD:
                    await smtp.login(s.SMTP_USERNAME, s.SMTP_PASSWORD)
                await smtp.send_message(msg)
        except aiosmtplib.SMTPException as exc:
            log.error(
                "smtp_error",
                error=str(exc),
                smtp_host=s.SMTP_HOST,
                smtp_port=s.SMTP_PORT,
            )
            raise
        except TimeoutError as exc:
            log.error("smtp_timeout", smtp_host=s.SMTP_HOST, smtp_port=s.SMTP_PORT)
            raise aiosmtplib.SMTPConnectTimeoutError(
                f"SMTP connection timed out after {s.EMAIL_TIMEOUT_SECONDS}s"
            ) from exc


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def get_email_service(
    settings: Settings = Depends(get_settings),
) -> EmailService:
    """FastAPI dependency — returns a per-request ``EmailService`` instance."""
    return EmailService(settings)
