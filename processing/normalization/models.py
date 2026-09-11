from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.source import SourceType


class NormalizedCandidate(BaseModel):
    """Deterministic, DB-independent transport model produced from a
    RawCandidate. Never mutates the source RawCandidate; always keeps the
    original raw value alongside its normalized form so nothing is lost.

    This is NOT a Company: MLE-004 stops here, dedup/matching decides in a
    later stage whether a NormalizedCandidate becomes a new Company or is
    merged into an existing one.
    """

    model_config = ConfigDict(extra="allow")

    external_id: str | None = None

    canonical_name: str
    normalized_name: str

    category: str | None = None
    description: str | None = None

    country: str | None = None
    region: str | None = None
    city: str | None = None
    normalized_city: str | None = None

    raw_address: str | None = None
    normalized_address: str | None = None

    phone_raw: str | None = None
    phone_normalized: str | None = None

    email_raw: str | None = None
    email_normalized: str | None = None

    website_raw: str | None = None
    website_url: str | None = None
    website_domain: str | None = None

    rating: float | None = None
    reviews_count: int | None = None

    source_type: SourceType
    source_url: str | None = None

    raw_payload: dict[str, Any] | None = None
