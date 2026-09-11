"""Company name normalization.

`canonical_name` preserves the trimmed original value (display form).
`normalized_name` is a deterministic, lowercase, legal-prefix-stripped form
meant for future dedup/matching — not for display.
"""

import re
import unicodedata

# Ukrainian legal-entity prefixes/abbreviations, stripped only as whole
# tokens (never as a substring of a real word).
LEGAL_PREFIXES = {
    "тов",
    "фоп",
    "пп",
    "прат",
    "пат",
    "ат",
    "дп",
    "кп",
}

_APOSTROPHES = "’ʼ`´‘"
_QUOTE_CHARS = '"«»“”„‟‹›'

_PUNCTUATION_TO_SPACE_RE = re.compile(r"[^\w']+", re.UNICODE)
_MULTISPACE_RE = re.compile(r"\s+")


def canonicalize_name(value: str) -> str:
    """Trim-only, display-safe form. Never lowercased, never stripped of
    legal prefixes.
    """
    return unicodedata.normalize("NFKC", value).strip()


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", value)

    for ch in _APOSTROPHES:
        text = text.replace(ch, "'")
    for ch in _QUOTE_CHARS:
        text = text.replace(ch, " ")

    text = text.lower()

    # Punctuation (except the apostrophe, which is meaningful inside
    # Ukrainian names) becomes a space so words don't get glued together.
    text = _PUNCTUATION_TO_SPACE_RE.sub(" ", text)

    tokens = [t for t in text.split() if t not in LEGAL_PREFIXES]
    return _MULTISPACE_RE.sub(" ", " ".join(tokens)).strip()
