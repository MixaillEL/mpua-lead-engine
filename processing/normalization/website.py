"""Website URL/domain normalization. Pure string transformation — no HTTP
requests, no alive/dead checks.
"""

from urllib.parse import urlsplit, urlunsplit


def _strip_www(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def _idna_domain(host: str) -> str:
    """Stable ASCII (punycode) canonical form. Falls back to the lowercase
    hostname if IDNA encoding fails, so we never crash on unusual input.
    """
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host


def normalize_website(value: str | None) -> tuple[str | None, str | None]:
    """Returns (website_url, website_domain)."""

    if not value or not value.strip():
        return None, None

    text = value.strip()

    if "://" not in text:
        text = f"https://{text}"

    parts = urlsplit(text)

    host = (parts.hostname or "").lower()
    if not host:
        return None, None

    path = parts.path or "/"

    canonical_url = urlunsplit((parts.scheme or "https", host, path, parts.query, ""))

    domain = _idna_domain(_strip_www(host))

    return canonical_url, domain
