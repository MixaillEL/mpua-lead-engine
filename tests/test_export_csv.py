from exporters.csv_exporter import rows_to_csv_bytes, sanitize_cell
from exporters.models import ExportRow


def _row(**overrides) -> ExportRow:
    defaults = dict(company_id="c1", company_name="Test Co")
    defaults.update(overrides)
    return ExportRow(**defaults)


def test_utf8_bom_present():
    content = rows_to_csv_bytes([_row()])
    assert content.startswith(b"\xef\xbb\xbf")


def test_ukrainian_text_roundtrips():
    content = rows_to_csv_bytes([_row(company_name="Клімат Сервіс", city="Дніпро")])
    text = content.decode("utf-8-sig")
    assert "Клімат Сервіс" in text
    assert "Дніпро" in text


def test_delimiter_is_semicolon_by_default():
    content = rows_to_csv_bytes([_row(company_name="A", category="B")])
    text = content.decode("utf-8-sig")
    header_line = text.splitlines()[0]
    assert ";" in header_line


def test_headers_present_and_ordered():
    content = rows_to_csv_bytes([_row()])
    text = content.decode("utf-8-sig")
    header_line = text.splitlines()[0]
    assert header_line.startswith("Company;Category;Country;Region;City;Address")


def test_formula_injection_is_neutralized():
    content = rows_to_csv_bytes([_row(company_name="=cmd|'/c calc'!A1")])
    text = content.decode("utf-8-sig")
    assert "'=cmd" in text
    assert "\n=cmd" not in text.replace("\r\n", "\n")


def test_formula_injection_variants():
    for trigger in ("=", "+", "-", "@"):
        assert sanitize_cell(f"{trigger}malicious", "company_name") == f"'{trigger}malicious"


def test_numeric_fields_never_prefixed():
    assert sanitize_cell(-5.0, "rating") == -5.0
    assert sanitize_cell(10, "reviews") == 10


def test_empty_export_has_header_only():
    content = rows_to_csv_bytes([])
    text = content.decode("utf-8-sig")
    lines = [l for l in text.splitlines() if l]
    assert len(lines) == 1


def test_multiple_rows_present():
    rows = [_row(company_id=f"c{i}", company_name=f"Company {i}") for i in range(5)]
    content = rows_to_csv_bytes(rows)
    text = content.decode("utf-8-sig")
    lines = [l for l in text.splitlines() if l]
    assert len(lines) == 6  # header + 5 rows


def test_only_valid_phone_email_exported():
    row = _row(phone_1="+380501234567", email_1="info@example.com")
    content = rows_to_csv_bytes([row])
    text = content.decode("utf-8-sig")
    assert "+380501234567" in text
    assert "info@example.com" in text
