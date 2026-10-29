"""Unit tests for Nest-ported open-domain helpers."""
from __future__ import annotations

from src.app.linq360.common.open_domains import (
    origins_match,
    parse_open_domains,
    request_matches_open_domain,
)


def test_parse_open_domains_json_array() -> None:
    assert parse_open_domains(
        '["https://dev1.linqmd.com","https://app.linqmd.com"]'
    ) == ["https://dev1.linqmd.com", "https://app.linqmd.com"]


def test_parse_open_domains_comma_separated() -> None:
    assert parse_open_domains("https://dev1.linqmd.com, https://app.linqmd.com") == [
        "https://dev1.linqmd.com",
        "https://app.linqmd.com",
    ]


def test_parse_open_domains_empty() -> None:
    assert parse_open_domains(None) == []
    assert parse_open_domains("") == []
    assert parse_open_domains("[]") == []
    # Non-array JSON is treated as a single comma-split token (Nest parity).
    assert parse_open_domains("{not-json}") == ["{not-json}"]
    assert parse_open_domains("[not-json]") == []


def test_origins_match_full_url_entry() -> None:
    assert origins_match(
        "https://dev1.linqmd.com/path",
        "https://dev1.linqmd.com",
    )
    assert not origins_match(
        "https://evil.example/path",
        "https://dev1.linqmd.com",
    )


def test_origins_match_host_only_entry() -> None:
    assert origins_match("https://dev1.linqmd.com/x", "dev1.linqmd.com")
    assert origins_match("https://dev1.linqmd.com:443/x", "dev1.linqmd.com:443")


def test_request_matches_open_domain_origin_or_referer() -> None:
    allow = ["https://dev1.linqmd.com", "https://app.linqmd.com"]
    assert request_matches_open_domain(
        "https://dev1.linqmd.com",
        None,
        allow,
    )
    assert request_matches_open_domain(
        None,
        "https://app.linqmd.com/dashboard",
        allow,
    )
    assert not request_matches_open_domain(
        "https://evil.example",
        None,
        allow,
    )
    assert not request_matches_open_domain(
        "https://dev1.linqmd.com",
        None,
        [],
    )
