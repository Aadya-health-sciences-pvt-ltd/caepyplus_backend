"""Tests for bulk upload template resolution."""
from __future__ import annotations

import csv
import io
from pathlib import Path

from app.core.bulk_upload_template import (
    build_bulk_upload_template_csv,
    get_bulk_upload_template_csv,
    read_packaged_template_csv_if_present,
)


def test_template_is_core_sections_not_legacy_48_col() -> None:
    text = get_bulk_upload_template_csv()
    header = next(ln for ln in text.splitlines() if ln.startswith("phone,"))
    assert header.startswith("phone,email,full_name")
    assert "first_name,last_name" not in header
    assert header.endswith(",theme")


def test_sample_rows_align_with_header() -> None:
    text = build_bulk_upload_template_csv()
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0]
    for line_no, data in enumerate(rows[1:], start=2):
        assert len(data) == len(header), f"row {line_no}: expected {len(header)} cols, got {len(data)}"


def test_sample_row_field_values_not_shifted() -> None:
    text = get_bulk_upload_template_csv()
    by_phone = {r["phone"]: r for r in csv.DictReader(io.StringIO(text))}
    assert by_phone["9876543210"]["year_of_mbbs"] == "2010"
    assert by_phone["9876543210"]["year_of_specialisation"] == "2015"
    assert by_phone["9123456780"]["year_of_mbbs"] == "2008"
    assert by_phone["9123456780"]["qualifications"] == "MS Orthopedics"
    assert by_phone["9123456780"]["theme"] == "dp_3"


def test_static_file_matches_builder_when_present() -> None:
    on_disk = read_packaged_template_csv_if_present()
    if on_disk is None:
        return
    assert on_disk == build_bulk_upload_template_csv()
