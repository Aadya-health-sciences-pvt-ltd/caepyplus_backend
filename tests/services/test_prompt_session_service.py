"""Unit tests for Prompt Session Service."""

import time

import pytest

from src.app.services.prompt_session_service import PromptSessionService, PromptUsageRecord


def test_prompt_usage_record_round_robin():
    """Test the round robin selection of prompt variants."""
    record = PromptUsageRecord()

    # First cycle
    assert record.get_next_variant(3) == 0
    assert record.get_next_variant(3) == 1
    assert record.get_next_variant(3) == 2

    # Second cycle
    assert record.get_next_variant(3) == 0
    assert record.cycle_count == 1

def test_prompt_usage_record_expiry():
    """Test expiry logic for usage records."""
    record = PromptUsageRecord()
    # Mock last accessed time to 2 days ago
    record.last_accessed = time.time() - (86400 * 2)
    assert record.is_expired(ttl_seconds=86400) is True

@pytest.mark.asyncio
async def test_service_get_next_variant():
    """Test getting next variant via service."""
    service = PromptSessionService()

    v1 = await service.get_next_variant("doc-1", "overview", 3)
    v2 = await service.get_next_variant("doc-1", "overview", 3)
    v3 = await service.get_next_variant("doc-1", "overview", 3)
    v4 = await service.get_next_variant("doc-1", "overview", 3)

    assert [v1, v2, v3, v4] == [0, 1, 2, 0]

    stats = await service.get_session_stats("doc-1")
    assert stats["sections"]["overview"]["total_calls"] == 4
    assert stats["sections"]["overview"]["cycle_count"] == 1

@pytest.mark.asyncio
async def test_service_clear_session():
    """Test clearing an entire session."""
    service = PromptSessionService()
    await service.get_next_variant("doc-1", "overview", 3)

    # Clear existing
    cleared = await service.clear_session("doc-1")
    assert cleared is True

    # Clear non-existing
    cleared2 = await service.clear_session("doc-1")
    assert cleared2 is False

    stats = await service.get_session_stats("doc-1")
    assert stats is None

@pytest.mark.asyncio
async def test_service_clear_section():
    """Test clearing a specific section."""
    service = PromptSessionService()
    await service.get_next_variant("doc-1", "overview", 3)
    await service.get_next_variant("doc-1", "about", 3)

    cleared = await service.clear_section("doc-1", "overview")
    assert cleared is True

    cleared2 = await service.clear_section("doc-1", "overview")
    assert cleared2 is False

    stats = await service.get_session_stats("doc-1")
    assert "about" in stats["sections"]
    assert "overview" not in stats["sections"]

@pytest.mark.asyncio
async def test_service_cleanup_expired():
    """Test cleanup of expired sessions."""
    service = PromptSessionService(ttl_seconds=10)

    await service.get_next_variant("doc-1", "overview", 3)

    # Force expiry by mutating last_accessed directly
    session = service._sessions["doc-1"]
    session.sections["overview"].last_accessed = time.time() - 20

    # Trigger cleanup
    service._last_cleanup = time.time() - 4000  # Force cleanup run
    await service._maybe_cleanup()

    assert await service.get_all_sessions_count() == 0
