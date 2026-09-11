"""Email normalization: trim + lowercase + basic syntactic validation.
No SMTP verification, no DNS/MX lookup.
"""

import re

# Deliberately simple syntactic check (RFC 5322 has near-infinite edge
# cases; we only need to reject obviously malformed input here).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None

    text = value.strip().lower()
    if not text:
        return None

    if not _EMAIL_RE.match(text):
        return None

    return text
