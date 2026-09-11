"""Pure HTML -> phones/emails/socials extraction. No network, no
normalization (that's processing.normalization, reused by the service).
"""

import json
import re

from bs4 import BeautifulSoup

from enrichment.website.models import ExtractedEmail, ExtractedPhone, ExtractedSocial

SOCIAL_DOMAINS = {
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "linkedin.com": "linkedin",
    "youtube.com": "youtube",
    "tiktok.com": "tiktok",
    "t.me": "telegram",
    "telegram.me": "telegram",
}

# Generic/placeholder addresses that show up in demo templates, never real
# leads.
EMAIL_GARBAGE_PATTERNS = (
    re.compile(r"^example@example\.\w+$", re.IGNORECASE),
    re.compile(r"^test@test\.\w+$", re.IGNORECASE),
    re.compile(r"^noreply@", re.IGNORECASE),
    re.compile(r"^no-reply@", re.IGNORECASE),
    re.compile(r"^you@", re.IGNORECASE),
    re.compile(r"^your@", re.IGNORECASE),
    re.compile(r"@yourdomain\.\w+$", re.IGNORECASE),
    re.compile(r"@domain\.\w+$", re.IGNORECASE),
    re.compile(r"\.(png|jpg|jpeg|gif|svg|webp)$", re.IGNORECASE),
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<![\d/])(\+?\d[\d\s().\-]{7,}\d)(?!\d)")

# "info [at] example [dot] com", "info(at)example.com", "info AT example DOT com"
_OBFUSCATION_SUBS = [
    (re.compile(r"\s*[\[(]\s*at\s*[\])]\s*", re.IGNORECASE), "@"),
    (re.compile(r"\s+at\s+", re.IGNORECASE), "@"),
    (re.compile(r"\s*[\[(]\s*dot\s*[\])]\s*", re.IGNORECASE), "."),
    (re.compile(r"\s+dot\s+", re.IGNORECASE), "."),
]


def _is_garbage_email(email: str) -> bool:
    return any(p.search(email) for p in EMAIL_GARBAGE_PATTERNS)


def _deobfuscate(text: str) -> str:
    for pattern, replacement in _OBFUSCATION_SUBS:
        text = pattern.sub(replacement, text)
    return text


def _social_platform(url: str) -> str | None:
    for domain, platform in SOCIAL_DOMAINS.items():
        if domain in url.lower():
            return platform
    return None


def _extract_json_ld(soup: BeautifulSoup) -> list[dict]:
    results = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict):
                results.append(item)
    return results


def extract_contacts(html: str, page_url: str) -> tuple[list[ExtractedPhone], list[ExtractedEmail], list[ExtractedSocial]]:
    soup = BeautifulSoup(html, "lxml")

    phones: list[ExtractedPhone] = []
    emails: list[ExtractedEmail] = []
    socials: list[ExtractedSocial] = []

    # --- tel: / mailto: links (confidence 1.0) ---
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("tel:"):
            raw = href[4:].strip()
            if raw:
                phones.append(ExtractedPhone(raw=raw, page_url=page_url, confidence=1.0))
        elif href.lower().startswith("mailto:"):
            raw = href[7:].split("?")[0].strip()
            if raw and not _is_garbage_email(raw.lower()):
                emails.append(ExtractedEmail(raw=raw, page_url=page_url, confidence=1.0))

        social_url = href if href.startswith("http") else None
        if social_url:
            platform = _social_platform(social_url)
            if platform:
                socials.append(ExtractedSocial(platform=platform, url=social_url, page_url=page_url))

    # --- JSON-LD (confidence 0.95) ---
    for item in _extract_json_ld(soup):
        tel = item.get("telephone")
        if isinstance(tel, str) and tel.strip():
            phones.append(ExtractedPhone(raw=tel.strip(), page_url=page_url, confidence=0.95))

        email = item.get("email")
        if isinstance(email, str) and email.strip() and not _is_garbage_email(email.lower()):
            emails.append(ExtractedEmail(raw=email.strip(), page_url=page_url, confidence=0.95))

        same_as = item.get("sameAs")
        same_as_list = same_as if isinstance(same_as, list) else ([same_as] if isinstance(same_as, str) else [])
        for url in same_as_list:
            if not isinstance(url, str):
                continue
            platform = _social_platform(url)
            if platform:
                socials.append(ExtractedSocial(platform=platform, url=url, page_url=page_url))

    # --- microdata itemprop=telephone / itemprop=email (confidence 0.9) ---
    for el in soup.find_all(attrs={"itemprop": "telephone"}):
        text = el.get("content") or el.get_text(strip=True)
        if text:
            phones.append(ExtractedPhone(raw=text, page_url=page_url, confidence=0.9))

    for el in soup.find_all(attrs={"itemprop": "email"}):
        text = el.get("content") or el.get_text(strip=True)
        if text and not _is_garbage_email(text.lower()):
            emails.append(ExtractedEmail(raw=text, page_url=page_url, confidence=0.9))

    # --- visible text (confidence 0.8) ---
    visible_text = soup.get_text(" ", strip=True)

    for match in _PHONE_RE.findall(visible_text):
        digits = re.sub(r"\D", "", match)
        if 7 <= len(digits) <= 15:
            phones.append(ExtractedPhone(raw=match.strip(), page_url=page_url, confidence=0.8))

    deobfuscated_text = _deobfuscate(visible_text)
    for match in _EMAIL_RE.findall(deobfuscated_text):
        if not _is_garbage_email(match.lower()):
            emails.append(ExtractedEmail(raw=match, page_url=page_url, confidence=0.8))

    return phones, emails, socials


def extract_links(html: str) -> list[tuple[str, str]]:
    """Returns (href, link_text) pairs for internal-link discovery."""
    soup = BeautifulSoup(html, "lxml")
    return [(a.get("href", ""), a.get_text(" ", strip=True)) for a in soup.find_all("a", href=True)]
