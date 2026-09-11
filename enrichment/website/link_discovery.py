"""URL normalization + same-domain contact/about link discovery for the
website crawler. Pure functions, no network.
"""

from urllib.parse import parse_qsl, urldefrag, urljoin, urlparse, urlunparse

CONTACT_KEYWORDS = {"contact", "contacts", "kontakt", "kontakty", "контакт", "контакти", "зв'язок"}
ABOUT_KEYWORDS = {"about", "about-us", "pro-nas", "про-нас", "про нас", "про-нас"}

TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}

SKIP_PATH_SEGMENTS = {"/login", "/signin", "/cart", "/checkout", "/search", "/wp-admin", "/admin"}


def normalize_url(url: str) -> str:
    """Strip fragment + tracking params, lowercase scheme/host, collapse
    duplicate trailing-slash variants — used for the crawl `visited` set.
    """

    url, _fragment = urldefrag(url)
    parts = urlparse(url)

    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()

    query_pairs = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS
    ]
    query = "&".join(f"{k}={v}" for k, v in query_pairs)

    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    return urlunparse((scheme, netloc, path, "", query, ""))


def is_same_domain(url: str, root_domain: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    return host == root_domain.lower()


def should_skip_path(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.startswith(seg) or seg in path for seg in SKIP_PATH_SEGMENTS)


def _link_priority(href: str, text: str) -> int:
    combined = f"{href} {text}".lower()
    if any(kw in combined for kw in CONTACT_KEYWORDS):
        return 0
    if any(kw in combined for kw in ABOUT_KEYWORDS):
        return 1
    return 2


def discover_contact_links(html_links: list[tuple[str, str]], base_url: str, root_domain: str) -> list[str]:
    """`html_links` is a list of (href, link_text) pairs from the homepage.
    Returns absolute, normalized, same-domain, non-skip URLs, contact links
    first, then about, deduplicated, in priority order.
    """

    scored: list[tuple[int, str]] = []
    seen: set[str] = set()

    for href, text in html_links:
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        absolute = urljoin(base_url, href)
        if not is_same_domain(absolute, root_domain):
            continue
        if should_skip_path(absolute):
            continue

        normalized = normalize_url(absolute)
        if normalized in seen:
            continue
        seen.add(normalized)

        priority = _link_priority(href, text)
        if priority < 2:  # only "relevant" (contact/about) links are followed
            scored.append((priority, normalized))

    scored.sort(key=lambda item: item[0])
    return [url for _, url in scored]
