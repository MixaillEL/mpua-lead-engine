"""Plain text normalization for free-form addresses/city/region strings.
No geocoding, no street-name correction, no postal-code inference.
"""

import re
import unicodedata

_MULTISPACE_RE = re.compile(r"\s+")
# Collapse comma/semicolon/colon separators to a single space. Periods are
# kept: Ukrainian address abbreviations ("вул.", "буд.", "просп.") rely on
# them and stripping would make the text harder to read/match.
_PUNCTUATION_RE = re.compile(r"[,;:]+")


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    text = unicodedata.normalize("NFKC", value).strip()
    if not text:
        return None

    text = _PUNCTUATION_RE.sub(" ", text)
    text = text.lower()
    text = _MULTISPACE_RE.sub(" ", text).strip()

    return text or None


def normalize_address(value: str | None) -> str | None:
    return normalize_text(value)


def normalize_city(value: str | None) -> str | None:
    return normalize_text(value)
