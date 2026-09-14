from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class ExportRow(BaseModel):
    """Client-facing export row — deliberately narrower than the internal
    schema. Only normalized/validated contact values ever appear here;
    internal-only fields (normalized_name, raw payloads, confidence
    scores, ...) are never exposed to the client file.
    """

    company_id: str

    company_name: str
    category: str | None = None

    country: str | None = None
    region: str | None = None
    city: str | None = None
    address: str | None = None

    phone_1: str | None = None
    phone_2: str | None = None
    phone_3: str | None = None

    email_1: str | None = None
    email_2: str | None = None
    email_3: str | None = None

    website: str | None = None

    facebook: str | None = None
    instagram: str | None = None
    telegram: str | None = None
    linkedin: str | None = None
    youtube: str | None = None
    tiktok: str | None = None

    rating: float | None = None
    reviews: int | None = None

    source_types: str | None = None
    source_urls: str | None = None

    first_seen: datetime | None = None
    last_seen: datetime | None = None


@dataclass
class ExportResult:
    job_run_id: str
    format: str
    path: Path
    rows: int
    bytes: int
    created_at: datetime
