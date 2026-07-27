"""Unit tests for bulk CSV row enrichment."""
from __future__ import annotations

from datetime import date

from app.core.bulk_csv_enrichment import (
    enrich_bulk_csv_row,
    parse_list_cell,
    resolve_full_name,
    validate_enriched_bulk_row,
)


def test_parse_list_cell_pipe_and_comma() -> None:
    assert parse_list_cell("English|Hindi") == ["English", "Hindi"]
    assert parse_list_cell("MBBS, MD") == ["MBBS", "MD"]
    assert parse_list_cell("a|a|b") == ["a", "b"]


def test_resolve_full_name_legacy_merge() -> None:
    assert resolve_full_name({"full_name": "Dr. X"}) == "Dr. X"
    assert resolve_full_name({
        "first_name": "Anjali",
        "last_name": "Sharma",
        "title": "Dr.",
    }) == "Dr. Anjali Sharma"


def test_enrich_derives_clinical_years_from_mbbs() -> None:
    current = date.today().year
    raw = {
        "phone": "9876543210",
        "email": "a@example.com",
        "full_name": "Dr. Test",
        "specialty": "Cardiology",
        "medical_registration_number": "REG1",
        "medical_council": "Council",
        "year_of_mbbs": str(current - 10),
    }
    enriched = enrich_bulk_csv_row(raw)
    assert enriched["years_of_clinical_experience"] == 10
    assert enriched["years_of_experience"] == 10


def test_enrich_city_and_practice_locations() -> None:
    raw = {
        "phone": "9876543210",
        "email": "a@example.com",
        "full_name": "Dr. Test",
        "specialty": "Cardiology",
        "medical_registration_number": "REG1",
        "medical_council": "Council",
        "city": "Bangalore",
        "practice_location": "Apollo | Main Rd | Bangalore | Karnataka",
    }
    enriched = enrich_bulk_csv_row(raw)
    assert enriched["primary_practice_location"] == "Bangalore"
    assert len(enriched["practice_locations"]) == 1
    assert enriched["practice_locations"][0].hospital_name == "Apollo"


def test_enrich_multiple_practice_locations_in_one_column() -> None:
    raw = {
        "phone": "9876543210",
        "email": "a@example.com",
        "full_name": "Dr. Test",
        "specialty": "Cardiology",
        "medical_registration_number": "REG1",
        "medical_council": "Council",
        "practice_location": (
            "Fortis | Mulund | Mumbai | Maharashtra ; "
            "Clinic | Andheri | Mumbai | Maharashtra"
        ),
    }
    enriched = enrich_bulk_csv_row(raw)
    assert len(enriched["practice_locations"]) == 2
    assert enriched["centres_of_practice"] == ["Fortis", "Clinic"]


def test_enrich_legacy_practice_location_columns() -> None:
    raw = {
        "phone": "9876543210",
        "email": "a@example.com",
        "full_name": "Dr. Test",
        "specialty": "Cardiology",
        "medical_registration_number": "REG1",
        "medical_council": "Council",
        "practice_location_1": "Apollo | Main Rd | Bangalore | Karnataka",
    }
    enriched = enrich_bulk_csv_row(raw)
    assert len(enriched["practice_locations"]) == 1
    assert enriched["centres_of_practice"] == ["Apollo"]


def test_validate_requires_specialty_and_full_name() -> None:
    raw = {"phone": "9876543210"}
    enriched = enrich_bulk_csv_row(raw)
    errors = validate_enriched_bulk_row(2, raw, enriched)
    fields = {e.field for e in errors}
    assert "full_name" in fields
    assert "email" in fields
    assert "specialty" in fields
    assert "medical_registration_number" in fields
    assert "medical_council" in fields


def test_validate_spec_before_mbbs_fails() -> None:
    raw = {
        "phone": "9876543210",
        "email": "a@example.com",
        "full_name": "Dr. Test",
        "specialty": "Cardiology",
        "medical_registration_number": "REG1",
        "medical_council": "Council",
        "year_of_mbbs": "2015",
        "year_of_specialisation": "2010",
    }
    enriched = enrich_bulk_csv_row(raw)
    errors = validate_enriched_bulk_row(2, raw, enriched)
    assert any(e.field == "year_of_specialisation" for e in errors)


def test_legacy_primary_specialization_alias() -> None:
    raw = {
        "phone": "9876543210",
        "email": "a@example.com",
        "full_name": "Dr. Test",
        "primary_specialization": "Neurology",
        "medical_registration_number": "REG1",
        "medical_council": "Council",
    }
    enriched = enrich_bulk_csv_row(raw)
    assert enriched["specialty"] == "Neurology"
