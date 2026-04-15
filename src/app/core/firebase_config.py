"""Firebase token verification for Google Sign-In.

Provides verify_firebase_token() which verifies Firebase ID tokens.
Uses firebase-admin SDK with an async fallback to Google's public token
verification endpoint for local development without a service account.

Required environment variables:
    FIREBASE_PROJECT_ID   – Firebase project ID (e.g. "my-project")
    FIREBASE_WEB_API_KEY  – Firebase Web API key (for the fallback path)
"""

import asyncio
import functools
import os
from dotenv import load_dotenv

load_dotenv()

from typing import Any

import firebase_admin  # type: ignore[import-untyped]
import httpx
import structlog
from firebase_admin import auth as firebase_auth

logger = structlog.get_logger(__name__)

FIREBASE_PROJECT_ID: str = os.environ.get("FIREBASE_PROJECT_ID", "")

# Set project ID env var for firebase-admin
if FIREBASE_PROJECT_ID:
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", FIREBASE_PROJECT_ID)

_firebase_app = None


def _init_firebase() -> None:
    """Initialize Firebase Admin SDK."""
    global _firebase_app
    if not FIREBASE_PROJECT_ID:
        raise ValueError(
            "FIREBASE_PROJECT_ID environment variable is not set. "
            "Google Sign-In cannot be used without it."
        )
    if _firebase_app is None:
        try:
            _firebase_app = firebase_admin.initialize_app(
                options={"projectId": FIREBASE_PROJECT_ID}
            )
            logger.info("Firebase Admin initialized", project_id=FIREBASE_PROJECT_ID)
        except ValueError:
            _firebase_app = firebase_admin.get_app()
            logger.info("Firebase Admin already initialized")


async def _verify_via_google_api_async(id_token: str) -> dict[str, Any]:
    """Verify Firebase ID token via Google's public API (async fallback).

    Uses an async HTTP client to avoid blocking the event loop.
    Suitable for local development without a Firebase service account.
    The API key is never included in exception messages to prevent leakage.
    """
    web_api_key = os.environ.get("FIREBASE_WEB_API_KEY", "")
    if not web_api_key:
        raise ValueError(
            "FIREBASE_WEB_API_KEY environment variable is not set. "
            "Cannot use Google API fallback for Firebase token verification."
        )
    # Build URL with key as query param — never echo in logs or errors.
    verify_url = (
        "https://identitytoolkit.googleapis.com/v1/accounts:lookup"
        f"?key={web_api_key}"
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(verify_url, json={"idToken": id_token})

    if response.status_code != 200:
        # Extract only the error message — never include the URL (contains API key).
        error_msg = response.json().get("error", {}).get("message", "Unknown error")
        raise ValueError(f"Google token verification failed: {error_msg}")

    data = response.json()
    users = data.get("users", [])

    if not users:
        raise ValueError("No user found for this token")

    user_info = users[0]

    # Build a decoded token dict matching firebase-admin's format
    return {
        "uid": user_info.get("localId", ""),
        "email": user_info.get("email", ""),
        "name": user_info.get("displayName", ""),
        "email_verified": user_info.get("emailVerified", False),
        "picture": user_info.get("photoUrl", ""),
    }


async def verify_firebase_token(id_token: str) -> dict[str, Any]:
    """Verify a Firebase ID token and return the decoded claims.

    Attempts firebase-admin SDK first.  ``firebase_auth.verify_id_token`` is a
    blocking synchronous call (it fetches Google public-key certs on first use
    and performs CPU-bound JWT verification on every call).  We offload it to
    the default thread-pool executor so the event loop is never stalled.

    Falls back to an async Google Identity Toolkit API call when the SDK
    fails (e.g. no service-account credentials in local dev).

    Args:
        id_token: The Firebase ID token string from the frontend.

    Returns:
        dict with keys like 'uid', 'email', 'name', 'email_verified', etc.

    Raises:
        ValueError: If the token is invalid or expired.
    """
    _init_firebase()
    loop = asyncio.get_event_loop()
    try:
        decoded_token = await loop.run_in_executor(
            None,
            functools.partial(firebase_auth.verify_id_token, id_token),
        )
        logger.info(
            "Firebase token verified (SDK)",
            uid=decoded_token.get("uid"),
            email=decoded_token.get("email"),
        )
        return decoded_token  # type: ignore[no-any-return]
    except Exception as e:
        sdk_error_str = str(e)
        logger.warning(
            "Firebase SDK verification failed, trying Google API fallback",
            error=sdk_error_str,
        )

    # Fallback: async verify via Google's public API.
    # HARD BLOCK IN PRODUCTION: The Google Identity Toolkit fallback requires
    # a web API key transmitted as a URL query parameter.  This is acceptable
    # only in local/development environments where a service-account credential
    # file is typically absent.  In production the Firebase Admin SDK MUST
    # succeed; if it does not, we fail hard rather than silently downgrade to
    # the less-secure fallback.
    app_env = os.environ.get("APP_ENV", "development").lower()
    if app_env == "production":
        logger.error(
            "Firebase SDK verification failed in production — rejecting token",
            error=sdk_error_str,
        )
        raise ValueError(
            "Firebase token verification failed. "
            "Ensure FIREBASE_PROJECT_ID is correct and the service account has "
            "the 'Firebase Authentication Admin' role."
        )

    try:
        decoded_token = await _verify_via_google_api_async(id_token)
        logger.info(
            "Firebase token verified (Google API fallback — DEV only)",
            uid=decoded_token.get("uid"),
            email=decoded_token.get("email"),
        )
        return decoded_token
    except Exception as api_error:
        # Log the detail internally but never surface it to the caller.
        logger.error("All token verification methods failed", error=str(api_error))
        raise ValueError("Firebase token verification failed") from api_error
