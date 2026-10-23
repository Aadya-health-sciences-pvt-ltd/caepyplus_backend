"""Parse Practice Hub pending-counts payloads and workspace token helpers."""
import base64
import json

import pytest

from src.app.linq360.services.practice_hub_pending_client import (
    PracticeHubPendingError,
    linqmd_user_id_from_workspace_token,
    parse_pending_counts,
    parse_pending_payload,
    workspace_identity_from_token,
)


def _jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}.sig"


def test_parse_pending_counts() -> None:
    counts = parse_pending_counts(
        {
            "user_id": 884,
            "reviews": {"pending_count": 2},
            "blog_comments": {"pending_count": 0},
            "podcast_comments": {"pending_count": 3},
        }
    )
    assert counts == {"reviews": 2, "blog_comments": 0, "podcast_comments": 3}


def test_parse_nested_content_keeps_id_arrays() -> None:
    payload = parse_pending_payload(
        {
            "content": {
                "reviews": {"pending_count": 1, "review_id": [3]},
                "blog_comments": {
                    "pending_count": 2,
                    "comment_id": [2, 4],
                    "blog_id": [5],
                },
                "podcast_comments": {
                    "pending_count": 1,
                    "comment_id": [2],
                    "podcast_id": [3],
                },
                "total_pending_counts": 4,
            },
            "payments": {},
            "requests": {},
            "appointments": {},
        }
    )
    assert payload["reviews"] == {"pending_count": 1, "review_id": [3]}
    assert payload["blog_comments"] == {
        "pending_count": 2,
        "comment_id": [2, 4],
        "blog_id": [5],
    }
    assert payload["podcast_comments"] == {
        "pending_count": 1,
        "comment_id": [2],
        "podcast_id": [3],
    }
    assert parse_pending_counts(
        {"content": payload, "total_pending_counts": 4}
    ) == {"reviews": 1, "blog_comments": 2, "podcast_comments": 1}


def test_parse_ignores_drupal_total() -> None:
    counts = parse_pending_counts(
        {
            "user_id": 246,
            "reviews": {"pending_count": 10},
            "blog_comments": {"pending_count": 2},
            "podcast_comments": {"pending_count": 5},
            "total_pending_counts": 99,
        }
    )
    assert counts == {"reviews": 10, "blog_comments": 2, "podcast_comments": 5}


def test_parse_floors_negative_and_missing() -> None:
    counts = parse_pending_counts({"reviews": {"pending_count": -4}})
    assert counts == {"reviews": 0, "blog_comments": 0, "podcast_comments": 0}


def test_linqmd_user_id_from_workspace_token() -> None:
    token = _jwt(
        {
            "user_id": "320",
            "appointment_doctor_id": "892",
            "email": "workspace7@gmail.com",
        }
    )
    assert linqmd_user_id_from_workspace_token(token) == "892"
    assert linqmd_user_id_from_workspace_token(f"Bearer {token}") == "892"


def test_workspace_identity_from_token() -> None:
    token = _jwt(
        {
            "user_id": "325",
            "workspace_id": "161",
            "appointment_doctor_id": "892",
            "email": "workspace7@gmail.com",
        }
    )
    identity = workspace_identity_from_token(f"Bearer {token}")
    assert identity == {
        "linqmd_user_id": "892",
        "workspace_id": 161,
        "ws_user_id": 325,
    }


def test_linqmd_user_id_missing_appointment_doctor() -> None:
    token = _jwt({"user_id": "320", "appointment_doctor_id": None})
    with pytest.raises(PracticeHubPendingError, match="appointment_doctor_id"):
        linqmd_user_id_from_workspace_token(token)
