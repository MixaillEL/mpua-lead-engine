from dataclasses import dataclass, field

from pydantic import BaseModel


@dataclass
class ExtractedPhone:
    raw: str
    page_url: str
    confidence: float


@dataclass
class ExtractedEmail:
    raw: str
    page_url: str
    confidence: float


@dataclass
class ExtractedSocial:
    platform: str
    url: str
    page_url: str


@dataclass
class PageFetchResult:
    url: str
    status_code: int | None
    html: str | None
    error: str | None = None


class WebsiteEnrichmentResult(BaseModel):
    """Transport model — not persisted as-is; a plain report of one
    enrich_company_website() run.
    """

    company_id: str
    website_url: str | None = None
    status: str = "ok"  # ok | skipped_no_website | error
    status_code: int | None = None
    is_alive: bool | None = None

    pages_requested: int = 0
    pages_successful: int = 0
    pages_failed: int = 0

    phones: list[str] = []
    emails: list[str] = []
    social_links: list[str] = []

    phones_added: int = 0
    emails_added: int = 0
    socials_added: int = 0

    errors: list[str] = []
    duration: float = 0.0


@dataclass
class WebsiteBatchStats:
    received: int
    with_website: int = 0
    skipped_no_website: int = 0
    attempted: int = 0
    alive: int = 0
    dead: int = 0
    failed: int = 0

    pages_requested: int = 0
    pages_successful: int = 0

    phones_found: int = 0
    phones_added: int = 0

    emails_found: int = 0
    emails_added: int = 0

    socials_found: int = 0
    socials_added: int = 0

    duration: float = 0.0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "received": self.received,
            "with_website": self.with_website,
            "skipped_no_website": self.skipped_no_website,
            "attempted": self.attempted,
            "alive": self.alive,
            "dead": self.dead,
            "failed": self.failed,
            "pages_requested": self.pages_requested,
            "pages_successful": self.pages_successful,
            "phones_found": self.phones_found,
            "phones_added": self.phones_added,
            "emails_found": self.emails_found,
            "emails_added": self.emails_added,
            "socials_found": self.socials_found,
            "socials_added": self.socials_added,
            "duration": round(self.duration, 3),
        }
