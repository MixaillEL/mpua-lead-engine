"""Deterministic RawCandidate -> NormalizedCandidate transformation.

No network calls, no DB access, no randomness, no dependency on wall-clock
time. Same input always produces the same output.
"""

import logging
from dataclasses import dataclass, field

from processing.normalization.address import normalize_address, normalize_city
from processing.normalization.company_name import canonicalize_name, normalize_name
from processing.normalization.email import normalize_email
from processing.normalization.models import NormalizedCandidate
from processing.normalization.phone import normalize_phone
from processing.normalization.website import normalize_website
from sources.schemas import RawCandidate

logger = logging.getLogger("mpua.processing.normalization")


def normalize_candidate(candidate: RawCandidate) -> NormalizedCandidate:
    """Pure function: never mutates `candidate`."""

    website_url, website_domain = normalize_website(candidate.website)

    return NormalizedCandidate(
        external_id=candidate.external_id,
        canonical_name=canonicalize_name(candidate.name),
        normalized_name=normalize_name(candidate.name),
        category=candidate.category,
        description=candidate.description,
        country=candidate.country,
        region=candidate.region,
        city=candidate.city,
        normalized_city=normalize_city(candidate.city),
        raw_address=candidate.raw_address,
        normalized_address=normalize_address(candidate.raw_address),
        phone_raw=candidate.phone,
        phone_normalized=normalize_phone(candidate.phone),
        email_raw=candidate.email,
        email_normalized=normalize_email(candidate.email),
        website_raw=candidate.website,
        website_url=website_url,
        website_domain=website_domain,
        rating=candidate.rating,
        reviews_count=candidate.reviews_count,
        source_type=candidate.source_type,
        source_url=candidate.source_url,
        raw_payload=candidate.raw_payload,
    )


@dataclass
class NormalizationStats:
    received: int
    normalized: int = 0
    failed: int = 0

    phones_present: int = 0
    phones_valid: int = 0
    phones_invalid: int = 0

    emails_present: int = 0
    emails_valid: int = 0
    emails_invalid: int = 0

    websites_present: int = 0
    domains_valid: int = 0
    domains_invalid: int = 0

    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "received": self.received,
            "normalized": self.normalized,
            "failed": self.failed,
            "phones_present": self.phones_present,
            "phones_valid": self.phones_valid,
            "phones_invalid": self.phones_invalid,
            "emails_present": self.emails_present,
            "emails_valid": self.emails_valid,
            "emails_invalid": self.emails_invalid,
            "websites_present": self.websites_present,
            "domains_valid": self.domains_valid,
            "domains_invalid": self.domains_invalid,
        }


def normalize_candidates(
    candidates: list[RawCandidate],
) -> tuple[list[NormalizedCandidate], NormalizationStats]:
    stats = NormalizationStats(received=len(candidates))
    results: list[NormalizedCandidate] = []

    for candidate in candidates:
        try:
            normalized = normalize_candidate(candidate)
            results.append(normalized)
            stats.normalized += 1

            if candidate.phone:
                stats.phones_present += 1
                if normalized.phone_normalized:
                    stats.phones_valid += 1
                else:
                    stats.phones_invalid += 1

            if candidate.email:
                stats.emails_present += 1
                if normalized.email_normalized:
                    stats.emails_valid += 1
                else:
                    stats.emails_invalid += 1

            if candidate.website:
                stats.websites_present += 1
                if normalized.website_domain:
                    stats.domains_valid += 1
                else:
                    stats.domains_invalid += 1

        except Exception as exc:  # noqa: BLE001 - isolate one bad candidate
            stats.failed += 1
            stats.errors.append(str(exc))
            logger.warning(
                "normalization: failed to normalize candidate",
                extra={"external_id": candidate.external_id, "error": str(exc)},
            )

    return results, stats
