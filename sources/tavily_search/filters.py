"""Result relevance filtering for Tavily Search discovery. Deterministic,
heuristic — not an ML classifier. Prefers skipping an ambiguous result over
creating a garbage company candidate.
"""

import re
from urllib.parse import urlparse

from processing.identity.signals import SHARED_DOMAINS

# Extends the MLE-005 shared-domain denylist with sources that specifically
# show up in web search (not maps/OSM) results.
SEARCH_DENYLIST: frozenset[str] = SHARED_DOMAINS | frozenset(
    {
        "wikipedia.org",
        "maps.google.com",
        "bing.com",
        "yandex.ua",
        "duckduckgo.com",
    }
)

# Known business directories/aggregators: a listing page on these is not
# itself "the company's official website".
DIRECTORY_DOMAINS: frozenset[str] = frozenset(
    {
        "hotline.ua",
        "zoon.com.ua",
        "kontakty.ua",
        "yellow-pages.com.ua",
        "vkursi.pro",
    }
)

DIRECTORY_PATH_HINTS = ("/company/", "/companies/", "/firm/", "/catalog/", "/directory/")

FILE_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".ppt", ".pptx")

# Listicle/news/blog heuristic denywords (title-level). Deliberately small
# and conservative — a real business name containing one of these words is
# rare, but false negatives here are acceptable (missed candidate) whereas
# false positives (an article treated as a Company) are not.
LISTICLE_DENYWORDS = (
    "топ ",
    "топ-",
    "кращі",
    "рейтинг",
    "список",
    "каталог",
    "огляд",
    "новини",
    "article",
    "blog",
)

TITLE_SUFFIXES_TO_STRIP = (
    " — офіційний сайт",
    " - офіційний сайт",
    " | офіційний сайт",
    " — official site",
    " - official site",
    " | official site",
    " — головна",
    " - головна",
    " | головна",
    " — home",
    " - home",
    " | home",
)


def get_domain(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host


def is_denylisted_domain(domain: str | None) -> bool:
    return bool(domain) and domain.lower() in SEARCH_DENYLIST


def is_directory_result(url: str, domain: str | None) -> bool:
    if domain and domain.lower() in DIRECTORY_DOMAINS:
        return True
    path = urlparse(url).path.lower()
    return any(hint in path for hint in DIRECTORY_PATH_HINTS)


def is_file_result(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(FILE_EXTENSIONS)


def is_listicle_title(title: str) -> bool:
    lowered = title.lower()
    return any(word in lowered for word in LISTICLE_DENYWORDS)


def clean_title(title: str) -> str:
    cleaned = title.strip()
    lowered = cleaned.lower()
    for suffix in TITLE_SUFFIXES_TO_STRIP:
        if lowered.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
            lowered = cleaned.lower()
    return cleaned


def is_valid_http_url(url: str) -> bool:
    parts = urlparse(url)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


_SEARCH_RESULT_PAGE_RE = re.compile(r"[?&](q|query|search)=", re.IGNORECASE)


def is_search_result_page(url: str) -> bool:
    return bool(_SEARCH_RESULT_PAGE_RE.search(url))


def is_relevant_result(title: str, url: str) -> bool:
    """Minimum acceptance filter: valid URL, non-empty title, not
    denylisted/directory/file/search-page/listicle.
    """

    if not title or not title.strip():
        return False
    if not is_valid_http_url(url):
        return False

    domain = get_domain(url)
    if is_denylisted_domain(domain):
        return False
    if is_directory_result(url, domain):
        return False
    if is_file_result(url):
        return False
    if is_search_result_page(url):
        return False
    if is_listicle_title(title):
        return False

    return True
