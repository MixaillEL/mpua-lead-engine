"""Phone normalization via the `phonenumbers` library. No guessing: a
number that can't be parsed/validated as a real number is left as
phone_normalized=None, with the original preserved in phone_raw.
"""

import phonenumbers

DEFAULT_REGION = "UA"


def normalize_phone(value: str | None, default_region: str = DEFAULT_REGION) -> str | None:
    if not value or not value.strip():
        return None

    try:
        parsed = phonenumbers.parse(value, default_region)
    except phonenumbers.NumberParseException:
        return None

    if not phonenumbers.is_valid_number(parsed):
        return None

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
