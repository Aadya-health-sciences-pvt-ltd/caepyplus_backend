"""Unit tests for LinQMD speciality username slug helpers."""
from __future__ import annotations

from src.app.services.linqmd_sync_service import LinQMDSyncService


class TestSpecialityUsernameSlug:
    def test_replaces_special_characters_with_spaces(self):
        raw = 'Consultant Pediatrician & allergy asthma specialist'
        normalized = LinQMDSyncService._normalize_speciality_text(raw)
        assert normalized == 'Consultant Pediatrician allergy asthma specialist'

    def test_truncates_long_speciality_at_word_boundaries(self):
        raw = 'Consultant Pediatrician & allergy asthma specialist'
        truncated = LinQMDSyncService._truncate_speciality_text(
            LinQMDSyncService._normalize_speciality_text(raw),
        )
        assert truncated == 'Consultant Pediatrician'

    def test_slugify_after_normalize_and_truncate(self):
        raw = 'Consultant Pediatrician & allergy asthma specialist'
        assert (
            LinQMDSyncService._speciality_username_slug(raw)
            == 'consultantpediatrician'
        )

    def test_short_speciality_unchanged(self):
        assert LinQMDSyncService._speciality_username_slug('Cardiology') == 'cardiology'

    def test_single_long_word_not_split(self):
        raw = 'Otorhinolaryngology'
        assert LinQMDSyncService._speciality_username_slug(raw) == 'otorhinolaryngology'
