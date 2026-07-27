"""
Row enrichment for doctor bulk CSV uploads.

Maps core / legacy column names to ``DoctorUpdate`` fields, parses list cells,
derives experience years from MBBS / specialisation years, and builds practice
location objects from the ``practice_location`` column (legacy: ``practice_location_1``…``3``).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, get_args, get_origin

from ..schemas.doctor import DoctorUpdate, PracticeLocationBase
from ..services.linqmd_sync_service import LINQMD_PROFILE_THEMES

DEFAULT_BULK_LINQMD_THEME = "dp_3"

# Mirror caepy_plus_front_end/src/lib/validation.ts
CREDENTIALS_YEAR_MIN = 1950


def credentials_year_max() -> int:
    return date.today().year


class BulkCsvRowError:
    """Lightweight row validation error (converted to API schema in doctors.py)."""

    __slots__ = ("field", "error")

    def __init__(self, field: str | None, error: str) -> None:
        self.field = field
        self.error = error


# Legacy bulk template columns (still accepted on upload).
_LEGACY_PRACTICE_LOCATION_COLUMNS = tuple(f"practice_location_{i}" for i in range(1, 4))

# Legacy list columns (48-col template) → canonical DoctorUpdate field.
_LEGACY_LIST_ALIASES: dict[str, str] = {
    "awards_recognition": "awards_academic_honours",
    "memberships": "professional_memberships",
}

# Direct CSV keys that map to a different DoctorUpdate field before list coercion.
_FIELD_ALIASES: dict[str, str] = {
    "city": "primary_practice_location",
    "primary_practice_location": "primary_practice_location",
    "primary_specialization": "specialty",
}


def _annotation_is_list(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin is list:
        return True
    if origin is type(None):
        return False
    args = get_args(annotation)
    return any(_annotation_is_list(a) for a in args if a is not type(None))


DOCTOR_UPDATE_LIST_FIELDS: frozenset[str] = frozenset(
    name
    for name, field in DoctorUpdate.model_fields.items()
    if _annotation_is_list(field.annotation)
)

_INT_FIELD_NAMES: frozenset[str] = frozenset({
    "year_of_mbbs",
    "year_of_specialisation",
    "years_of_clinical_experience",
    "years_post_specialisation",
    "years_of_experience",
    "registration_year",
})

_FLOAT_FIELD_NAMES: frozenset[str] = frozenset({"consultation_fee"})


def parse_list_cell(raw: str | None) -> list[str]:
    """Split a cell on ``|``, ``,``, or ``;``; strip, drop empties, dedupe (order preserved)."""
    if not raw or not str(raw).strip():
        return []
    parts = re.split(r"[|,;]", str(raw))
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        item = part.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def resolve_full_name(raw: dict[str, str]) -> str:
    """Core template uses ``full_name``; legacy rows may only have first/last/title."""
    full = (raw.get("full_name") or "").strip()
    if full:
        return full
    first = (raw.get("first_name") or "").strip()
    last = (raw.get("last_name") or "").strip()
    title = (raw.get("title") or "").strip()
    merged = " ".join(p for p in (title, first, last) if p).strip()
    return merged


def _parse_practice_location_cell(cell: str) -> PracticeLocationBase | None:
    parts = [p.strip() for p in cell.split("|")]
    while len(parts) < 4:
        parts.append("")
    hospital, address, city, state = (parts[i] if parts[i] else None for i in range(4))
    if not any((hospital, address, city, state)):
        return None
    return PracticeLocationBase(
        hospital_name=hospital,
        address=address,
        city=city,
        state=state,
    )


def _practice_location_cells_from_row(raw: dict[str, str]) -> list[str]:
    """
    Collect practice-location segments from CSV.

    Core template: one ``practice_location`` cell; multiple sites separated by ``;``
    (each site: ``Hospital | Address | City | State``). Legacy uploads may use
    ``practice_location_1`` … ``practice_location_3`` instead.
    """
    cells: list[str] = []
    merged = (raw.get("practice_location") or "").strip()
    if merged:
        for segment in merged.split(";"):
            segment = segment.strip()
            if segment:
                cells.append(segment)
    for col in _LEGACY_PRACTICE_LOCATION_COLUMNS:
        cell = (raw.get(col) or "").strip()
        if cell:
            cells.append(cell)
    return cells


def _parse_int_cell(raw: str) -> int | None:
    text = (raw or "").strip()
    if not text:
        return None
    if not re.fullmatch(r"\d+", text):
        return None
    return int(text)


def _parse_float_cell(raw: str) -> float | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _merge_list_field(target: dict[str, Any], field: str, values: list[str]) -> None:
    if not values:
        return
    existing = target.get(field)
    if isinstance(existing, list):
        seen = set(existing)
        for v in values:
            if v not in seen:
                existing.append(v)
                seen.add(v)
    else:
        target[field] = values


def enrich_bulk_csv_row(raw: dict[str, str]) -> dict[str, Any]:
    """
    Transform a normalised CSV row (lower-case keys, stripped strings) into a
    ``DoctorUpdate``-compatible dict (proper list/int types).
    """
    enriched: dict[str, Any] = {}

    full_name = resolve_full_name(raw)
    if full_name:
        enriched["full_name"] = full_name

    email = (raw.get("email") or "").strip().lower()
    if email:
        enriched["email"] = email

    specialty = (raw.get("specialty") or raw.get("primary_specialization") or "").strip()
    if specialty:
        enriched["specialty"] = specialty
        enriched["primary_specialization"] = specialty

    for csv_key, du_key in _FIELD_ALIASES.items():
        val = (raw.get(csv_key) or "").strip()
        if val and du_key not in enriched:
            enriched[du_key] = val

    for field in (
        "medical_registration_number",
        "medical_council",
        "registration_authority",
        "what_patients_value_most",
        "approach_to_care",
        "availability_philosophy",
        "quality_time_interests_text",
        "professional_achievement",
        "personal_achievement",
        "professional_aspiration",
        "personal_aspiration",
    ):
        val = (raw.get(field) or "").strip()
        if val:
            enriched[field] = val

    for int_field in _INT_FIELD_NAMES:
        parsed = _parse_int_cell(raw.get(int_field, ""))
        if parsed is not None:
            enriched[int_field] = parsed

    fee = _parse_float_cell(raw.get("consultation_fee", ""))
    if fee is not None:
        enriched["consultation_fee"] = fee

    # List fields: canonical names + legacy aliases
    list_sources: dict[str, str] = {}
    for name in DOCTOR_UPDATE_LIST_FIELDS:
        list_sources[name] = name
    for legacy, canonical in _LEGACY_LIST_ALIASES.items():
        list_sources.setdefault(legacy, canonical)

    for csv_col, du_field in list_sources.items():
        cell = raw.get(csv_col, "")
        if not cell:
            continue
        _merge_list_field(enriched, du_field, parse_list_cell(cell))

    # Awards: merge both legacy and canonical columns
    awards_extra = parse_list_cell(raw.get("awards_academic_honours", ""))
    awards_legacy = parse_list_cell(raw.get("awards_recognition", ""))
    if awards_legacy:
        _merge_list_field(enriched, "awards_academic_honours", awards_legacy)
    if awards_extra:
        _merge_list_field(enriched, "awards_academic_honours", awards_extra)

    # Practice locations from practice_location (and legacy practice_location_1..3)
    practice_locations: list[PracticeLocationBase] = []
    hospital_names: list[str] = []
    for cell in _practice_location_cells_from_row(raw):
        loc = _parse_practice_location_cell(cell)
        if loc:
            practice_locations.append(loc)
            if loc.hospital_name:
                hospital_names.append(loc.hospital_name)

    if practice_locations:
        enriched["practice_locations"] = practice_locations
    if hospital_names:
        _merge_list_field(enriched, "centres_of_practice", hospital_names)

    # Passthrough: any remaining DoctorUpdate column present in the CSV
    skip_keys = {
        "phone",
        "first_name",
        "last_name",
        "title",
        "city",
        "practice_location",
        *_LEGACY_PRACTICE_LOCATION_COLUMNS,
        *list(_LEGACY_LIST_ALIASES.keys()),
        "awards_academic_honours",
        "awards_recognition",
        "specialty",
        "primary_specialization",
        "full_name",
        "email",
        "theme",
    }
    for col, val in raw.items():
        if col.startswith("_") or col in skip_keys or not val:
            continue
        if col not in DoctorUpdate.model_fields or col in enriched:
            continue
        if col in DOCTOR_UPDATE_LIST_FIELDS:
            _merge_list_field(enriched, col, parse_list_cell(val))
        elif col in _INT_FIELD_NAMES:
            parsed = _parse_int_cell(val)
            if parsed is not None:
                enriched[col] = parsed
        elif col in _FLOAT_FIELD_NAMES:
            parsed = _parse_float_cell(val)
            if parsed is not None:
                enriched[col] = parsed
        else:
            enriched[col] = val.strip()

    _derive_experience_years(enriched)
    return enriched


def _derive_experience_years(enriched: dict[str, Any]) -> None:
    current = credentials_year_max()
    mbbs = enriched.get("year_of_mbbs")
    spec = enriched.get("year_of_specialisation")

    if isinstance(mbbs, int) and enriched.get("years_of_clinical_experience") is None:
        enriched["years_of_clinical_experience"] = max(0, current - mbbs)
    if isinstance(spec, int) and enriched.get("years_post_specialisation") is None:
        enriched["years_post_specialisation"] = max(0, current - spec)
    clinical = enriched.get("years_of_clinical_experience")
    if clinical is not None and enriched.get("years_of_experience") is None:
        enriched["years_of_experience"] = clinical


def validate_enriched_bulk_row(
    row_num: int,
    raw: dict[str, str],
    enriched: dict[str, Any],
) -> list[BulkCsvRowError]:
    """Core required fields and credentials year rules (after enrichment)."""
    errors: list[BulkCsvRowError] = []
    _ = row_num  # callers attach row when converting to API errors

    if not enriched.get("full_name"):
        errors.append(BulkCsvRowError("full_name", "Full name is required."))

    if not enriched.get("email"):
        errors.append(BulkCsvRowError("email", "Email is required."))

    if not enriched.get("specialty"):
        errors.append(BulkCsvRowError(
            "specialty",
            "Specialty is required (column ``specialty`` or legacy ``primary_specialization``).",
        ))

    if not enriched.get("medical_registration_number"):
        errors.append(BulkCsvRowError(
            "medical_registration_number",
            "Medical registration number is required.",
        ))

    if not enriched.get("medical_council"):
        errors.append(BulkCsvRowError("medical_council", "Medical council is required."))

    year_max = credentials_year_max()
    mbbs = enriched.get("year_of_mbbs")
    spec = enriched.get("year_of_specialisation")

    if raw.get("year_of_mbbs", "").strip() and mbbs is None:
        errors.append(BulkCsvRowError("year_of_mbbs", "Enter a valid year of MBBS."))
    elif isinstance(mbbs, int) and (mbbs < CREDENTIALS_YEAR_MIN or mbbs > year_max):
        errors.append(BulkCsvRowError(
            "year_of_mbbs",
            f"Year of MBBS must be between {CREDENTIALS_YEAR_MIN} and {year_max}.",
        ))

    if raw.get("year_of_specialisation", "").strip() and spec is None:
        errors.append(BulkCsvRowError(
            "year_of_specialisation",
            "Enter a valid year of specialisation.",
        ))
    elif isinstance(spec, int) and (spec < CREDENTIALS_YEAR_MIN or spec > year_max):
        errors.append(BulkCsvRowError(
            "year_of_specialisation",
            f"Year of specialisation must be between {CREDENTIALS_YEAR_MIN} and {year_max}.",
        ))

    if isinstance(mbbs, int) and isinstance(spec, int) and spec < mbbs:
        errors.append(BulkCsvRowError(
            "year_of_specialisation",
            "Year of specialisation must be greater than or equal to year of MBBS.",
        ))

    return errors


def validate_bulk_csv_theme(raw: dict[str, str]) -> BulkCsvRowError | None:
    """Return a row error if ``theme`` is present but not a valid LinQMD profile theme."""
    theme_cell = (raw.get("theme") or "").strip().lower()
    if not theme_cell:
        return None
    if theme_cell not in LINQMD_PROFILE_THEMES:
        allowed = ", ".join(sorted(LINQMD_PROFILE_THEMES))
        return BulkCsvRowError(
            "theme",
            f"Invalid theme '{theme_cell}'. Must be one of: {allowed}.",
        )
    return None


def resolve_bulk_linqmd_theme(stored_row: dict[str, Any]) -> str:
    """LinQMD theme for bulk confirm — from ``_linqmd_theme`` or template default."""
    theme = stored_row.get("_linqmd_theme")
    if isinstance(theme, str) and theme.strip():
        return theme.strip().lower()
    return DEFAULT_BULK_LINQMD_THEME
