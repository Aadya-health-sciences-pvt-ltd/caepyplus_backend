"""Parse Practice Hub pending-counts payloads."""
from src.app.linq360.services.practice_hub_pending_client import parse_pending_counts


def test_parse_pending_counts() -> None:
    counts = parse_pending_counts(
        {
            "user_id": 884,
            "reviews": {"pending_count": 2},
            "blog_comments": {"pending_count": 0},
            "podcast_comments": {"pending_count": 3},
        }
    )
    assert counts == {
        "reviews_pending_count": 2,
        "blog_comments_pending_count": 0,
        "podcast_comments_pending_count": 3,
    }


def test_parse_floors_negative_and_missing() -> None:
    counts = parse_pending_counts({"reviews": {"pending_count": -4}})
    assert counts["reviews_pending_count"] == 0
    assert counts["blog_comments_pending_count"] == 0
    assert counts["podcast_comments_pending_count"] == 0
