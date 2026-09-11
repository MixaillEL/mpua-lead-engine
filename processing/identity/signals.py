"""Deterministic identity signals. No fuzzy/AI/embedding matching — only
exact-value comparisons on already-normalized fields.

Scoring policy (documented, thresholds adjustable but must stay documented
here):

    same source external_id   -> 100  (idempotency: reprocessing the exact
                                        same source record must resolve to
                                        the same Company)
    same normalized phone     -> 100
    same business website domain (not in SHARED_DOMAINS) -> 100
    same exact email address  ->  90
    same normalized_name + normalized_address (both exact) -> 90
    same normalized_name + normalized_city (both exact)    -> 70

    score >= 90  -> MATCH   (any single 100-weight signal already clears
                             this; email/name+address alone also clear it)
    60 <= score < 90 -> REVIEW (never auto-merged)
    score < 60   -> NEW

False positives (merging two different real companies) are worse than
false negatives (missing a duplicate, left as REVIEW/NEW) — see
processing/identity/resolver.py.
"""

from dataclasses import dataclass, field

# Domains that many unrelated businesses share (social platforms,
# marketplaces, link aggregators) and therefore must NEVER be treated as a
# company-identity signal.
SHARED_DOMAINS: frozenset[str] = frozenset(
    {
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "youtube.com",
        "tiktok.com",
        "t.me",
        "telegram.me",
        "prom.ua",
        "olx.ua",
        "google.com",
    }
)

# Free/consumer email providers: an exact matching address on one of these
# domains can still be a signal, but the *domain* itself must never be
# treated as a company-identity signal (two different people using gmail.com
# are not the same company).
FREE_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "ukr.net",
        "i.ua",
        "meta.ua",
        "outlook.com",
        "hotmail.com",
        "yahoo.com",
    }
)

SIGNAL_WEIGHTS: dict[str, int] = {
    "same_source_external_id": 100,
    "same_phone": 100,
    "same_domain": 100,
    "same_email": 90,
    "same_name_address": 90,
    "same_name_city": 70,
}


@dataclass
class MatchCandidate:
    """Lightweight projection of one existing Company, loaded via indexed
    queries — never a full ORM graph fetch of every Company in the DB.
    """

    company_id: str
    normalized_name: str
    normalized_city: str | None
    phones: frozenset[str] = field(default_factory=frozenset)
    emails: frozenset[str] = field(default_factory=frozenset)
    domains: frozenset[str] = field(default_factory=frozenset)
    normalized_addresses: frozenset[str] = field(default_factory=frozenset)
    external_ids: frozenset[tuple[str, str]] = field(default_factory=frozenset)


def is_shared_domain(domain: str | None) -> bool:
    return bool(domain) and domain.lower() in SHARED_DOMAINS


def is_free_email_domain(domain: str | None) -> bool:
    return bool(domain) and domain.lower() in FREE_EMAIL_DOMAINS


def evaluate_signals(
    *,
    normalized_name: str,
    normalized_city: str | None,
    normalized_address: str | None,
    phone_normalized: str | None,
    email_normalized: str | None,
    website_domain: str | None,
    source_type: str | None,
    external_id: str | None,
    match: MatchCandidate,
) -> tuple[int, list[str]]:
    """Return (score capped at 100, list of triggered signal names)."""

    triggered: list[str] = []

    if source_type and external_id and (source_type, external_id) in match.external_ids:
        triggered.append("same_source_external_id")

    if phone_normalized and phone_normalized in match.phones:
        triggered.append("same_phone")

    if website_domain and not is_shared_domain(website_domain) and website_domain in match.domains:
        triggered.append("same_domain")

    if email_normalized and email_normalized in match.emails:
        triggered.append("same_email")

    if (
        normalized_address
        and normalized_name == match.normalized_name
        and normalized_address in match.normalized_addresses
    ):
        triggered.append("same_name_address")

    if (
        normalized_city
        and normalized_name == match.normalized_name
        and normalized_city == match.normalized_city
    ):
        triggered.append("same_name_city")

    score = min(100, sum(SIGNAL_WEIGHTS[s] for s in triggered))
    return score, triggered
