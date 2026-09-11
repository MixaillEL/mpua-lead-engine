import pytest

from processing.normalization.email import normalize_email


def test_uppercase_email_is_lowercased():
    assert normalize_email("INFO@EXAMPLE.COM") == "info@example.com"


def test_email_with_surrounding_whitespace_is_trimmed():
    assert normalize_email(" info@example.com") == "info@example.com"


@pytest.mark.parametrize("raw", ["abc", "@", "a@", "not-an-email", ""])
def test_invalid_emails_return_none(raw):
    assert normalize_email(raw) is None


def test_none_returns_none():
    assert normalize_email(None) is None
