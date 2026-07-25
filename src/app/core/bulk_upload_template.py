"""
Canonical doctor bulk-upload CSV template (Sections 1–2).

Built with the stdlib ``csv`` module so columns stay aligned in Excel and in
upload parsing. Served for download; the static file is kept in sync for packaging.
"""
from __future__ import annotations

import csv
import io
from importlib import resources
from pathlib import Path

import app as app_pkg

_TEMPLATE_FILENAME = "doctor_bulk_upload_template.csv"

_TEMPLATE_COLUMNS: tuple[str, ...] = (
    "phone",
    "email",
    "full_name",
    "specialty",
    "city",
    "languages",
    "medical_registration_number",
    "medical_council",
    "practice_location",
    "year_of_mbbs",
    "year_of_specialisation",
    "qualifications",
    "awards_academic_honours",
    "years_of_clinical_experience",
    "years_post_specialisation",
    "theme",
)

_SAMPLE_ROWS: tuple[dict[str, str], ...] = (
    {
        "phone": "9876543210",
        "email": "anjali.sharma@example.com",
        "full_name": "Dr. Anjali Sharma",
        "specialty": "Cardiology",
        "city": "Bangalore",
        "languages": "English|Hindi",
        "medical_registration_number": "KMC12345",
        "medical_council": "Karnataka Medical Council",
        "practice_location": (
            "Apollo Hospital | 154 Bannerghatta Road | Bangalore | Karnataka"
        ),
        "year_of_mbbs": "2010",
        "year_of_specialisation": "2015",
        "qualifications": "MBBS|MD Cardiology",
        "awards_academic_honours": "Best Resident 2014",
        "years_of_clinical_experience": "",
        "years_post_specialisation": "",
        "theme": "dp_3",
    },
    {
        "phone": "9123456780",
        "email": "raj.patel@example.com",
        "full_name": "Dr. Raj Patel",
        "specialty": "Orthopedics",
        "city": "Mumbai",
        "languages": "English|Marathi|Hindi",
        "medical_registration_number": "MCI67890",
        "medical_council": "Maharashtra Medical Council",
        "practice_location": (
            "Fortis Hospital | Mulund West | Mumbai | Maharashtra ; "
            "Sushrut Clinic | Andheri East | Mumbai | Maharashtra"
        ),
        "year_of_mbbs": "2008",
        "year_of_specialisation": "",
        "qualifications": "MS Orthopedics",
        "awards_academic_honours": "",
        "years_of_clinical_experience": "",
        "years_post_specialisation": "",
        "theme": "dp_3",
    },
)


def build_bulk_upload_template_csv() -> str:
    """Render the template CSV (header + sample rows)."""
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(_TEMPLATE_COLUMNS),
        lineterminator="\n",
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in _SAMPLE_ROWS:
        writer.writerow(row)
    return buffer.getvalue()


def get_bulk_upload_template_csv() -> str:
    """Return UTF-8 CSV text for the Sections 1–2 bulk upload template."""
    return build_bulk_upload_template_csv()


def _template_path_on_disk() -> Path:
    return Path(app_pkg.__file__).resolve().parent / "static" / _TEMPLATE_FILENAME


def read_packaged_template_csv_if_present() -> str | None:
    """Optional on-disk copy (e.g. wheel); None if missing."""
    path = _template_path_on_disk()
    if path.is_file():
        return path.read_text(encoding="utf-8")
    try:
        ref = resources.files("app.static").joinpath(_TEMPLATE_FILENAME)
        return ref.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, TypeError, OSError):
        return None
