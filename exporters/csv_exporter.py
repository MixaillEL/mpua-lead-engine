"""CSV export: UTF-8 with BOM (Excel-on-Windows-friendly), configurable
delimiter, formula-injection safe.
"""

import csv
import io

from app.core.config import get_settings
from exporters.models import ExportRow

COLUMNS: list[tuple[str, str]] = [
    ("Company", "company_name"),
    ("Category", "category"),
    ("Country", "country"),
    ("Region", "region"),
    ("City", "city"),
    ("Address", "address"),
    ("Phone 1", "phone_1"),
    ("Phone 2", "phone_2"),
    ("Phone 3", "phone_3"),
    ("Email 1", "email_1"),
    ("Email 2", "email_2"),
    ("Email 3", "email_3"),
    ("Website", "website"),
    ("Facebook", "facebook"),
    ("Instagram", "instagram"),
    ("Telegram", "telegram"),
    ("LinkedIn", "linkedin"),
    ("YouTube", "youtube"),
    ("TikTok", "tiktok"),
    ("Rating", "rating"),
    ("Reviews", "reviews"),
    ("Source Types", "source_types"),
    ("Source URLs", "source_urls"),
    ("First Seen", "first_seen"),
    ("Last Seen", "last_seen"),
]

# Fields that are genuinely numeric and must never get the CSV/Excel
# formula-injection text prefix.
NUMERIC_FIELDS = {"rating", "reviews"}

_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@")


def sanitize_cell(value, field_name: str):
    """Neutralize CSV/Excel formula injection: a text cell whose value
    starts with =, +, -, or @ gets a leading apostrophe. Numeric fields
    (rating/reviews) and non-string values are left untouched.
    """

    if field_name in NUMERIC_FIELDS or value is None:
        return value
    if not isinstance(value, str):
        return value
    if value.startswith(_FORMULA_TRIGGER_CHARS):
        return "'" + value
    return value


def rows_to_csv_bytes(rows: list[ExportRow], delimiter: str | None = None) -> bytes:
    delimiter = delimiter or get_settings().EXPORT_CSV_DELIMITER

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\r\n")

    writer.writerow([header for header, _ in COLUMNS])

    for row in rows:
        data = row.model_dump()
        writer.writerow(
            [sanitize_cell(data.get(field), field) if data.get(field) is not None else "" for _, field in COLUMNS]
        )

    text = buffer.getvalue()
    return b"\xef\xbb\xbf" + text.encode("utf-8")
