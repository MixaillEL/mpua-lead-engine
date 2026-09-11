import pytest

from processing.normalization.phone import normalize_phone


@pytest.mark.parametrize(
    "raw",
    [
        "0501234567",
        "+380501234567",
        "380501234567",
        "+38 (050) 123-45-67",
        "050 123 45 67",
    ],
)
def test_equivalent_ua_numbers_normalize_the_same(raw):
    assert normalize_phone(raw) == "+380501234567"


def test_invalid_phone_returns_none():
    assert normalize_phone("not a phone") is None


def test_too_short_number_returns_none():
    assert normalize_phone("123") is None


def test_empty_string_returns_none():
    assert normalize_phone("") is None


def test_none_returns_none():
    assert normalize_phone(None) is None


def test_foreign_valid_number_is_normalized():
    # US number, explicit country code so default_region=UA doesn't matter
    assert normalize_phone("+1 650 253 0000") == "+16502530000"
