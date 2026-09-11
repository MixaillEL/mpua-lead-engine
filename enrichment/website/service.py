"""Company -> website -> contacts pipeline. Never creates/merges a
Company or reruns identity resolution — it only adds contacts to an
existing Company (idempotent, via the MLE-005 unique constraints).
"""

import logging
import time
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.company_email import CompanyEmail
from app.models.company_phone import CompanyPhone
from app.models.company_website import CompanyWebsite
from app.models.social_link import SocialLink, SocialPlatform, url_fingerprint
from app.models.source import Source, SourceType
from enrichment.website.crawler import WebsiteCrawler
from enrichment.website.extractor import extract_contacts
from enrichment.website.models import WebsiteBatchStats, WebsiteEnrichmentResult
from processing.identity.signals import SHARED_DOMAINS
from processing.normalization.email import normalize_email
from processing.normalization.phone import normalize_phone

logger = logging.getLogger("mpua.enrichment.website")


def _pick_website(db: Session, company_id: str) -> CompanyWebsite | None:
    websites = db.scalars(
        select(CompanyWebsite).where(CompanyWebsite.company_id == company_id)
    ).all()

    crawlable = [w for w in websites if w.domain and w.domain.lower() not in SHARED_DOMAINS]
    if not crawlable:
        return None

    alive = [w for w in crawlable if w.is_alive]
    if alive:
        return alive[0]

    return crawlable[0]


def _get_or_create_website_source(db: Session, page_url: str) -> Source:
    existing = db.scalar(
        select(Source).where(Source.source_type == SourceType.website, Source.source_url == page_url)
    )
    if existing is not None:
        return existing

    source = Source(source_type=SourceType.website, source_url=page_url)
    db.add(source)
    db.flush()
    return source


def _persist_phone(db: Session, company_id: str, phone_normalized: str, phone_raw: str, source_id: str, confidence: float) -> bool:
    existing = db.scalar(
        select(CompanyPhone).where(
            CompanyPhone.company_id == company_id, CompanyPhone.phone_normalized == phone_normalized
        )
    )
    if existing is not None:
        return False

    db.add(
        CompanyPhone(
            company_id=company_id,
            phone_raw=phone_raw,
            phone_normalized=phone_normalized,
            source_id=source_id,
            confidence=confidence,
        )
    )
    db.flush()
    return True


def _persist_email(db: Session, company_id: str, email_normalized: str, source_id: str, confidence: float) -> bool:
    existing = db.scalar(
        select(CompanyEmail).where(
            CompanyEmail.company_id == company_id, CompanyEmail.email == email_normalized
        )
    )
    if existing is not None:
        return False

    domain = email_normalized.rsplit("@", 1)[-1]
    db.add(
        CompanyEmail(
            company_id=company_id,
            email=email_normalized,
            domain=domain,
            source_id=source_id,
            confidence=confidence,
        )
    )
    db.flush()
    return True


def _persist_social(db: Session, company_id: str, platform: str, url: str, source_id: str) -> bool:
    try:
        platform_enum = SocialPlatform(platform)
    except ValueError:
        platform_enum = SocialPlatform.other

    fingerprint = url_fingerprint(url)
    existing = db.scalar(
        select(SocialLink).where(
            SocialLink.company_id == company_id,
            SocialLink.platform == platform_enum,
            SocialLink.url_fingerprint == fingerprint,
        )
    )
    if existing is not None:
        return False

    db.add(
        SocialLink(
            company_id=company_id,
            platform=platform_enum,
            url=url,
            url_fingerprint=fingerprint,
            source_id=source_id,
        )
    )
    db.flush()
    return True


async def enrich_company_website(
    db: Session, company_id: str, crawler: WebsiteCrawler | None = None
) -> WebsiteEnrichmentResult:
    started = time.monotonic()

    company = db.get(Company, company_id)
    if company is None:
        raise ValueError(f"Company {company_id} not found")

    website = _pick_website(db, company_id)
    if website is None:
        return WebsiteEnrichmentResult(
            company_id=company_id, website_url=None, status="skipped_no_website"
        )

    result = WebsiteEnrichmentResult(company_id=company_id, website_url=website.url)

    try:
        crawler = crawler or WebsiteCrawler()
        pages = await crawler.crawl(website.url)
    except Exception as exc:  # noqa: BLE001 - one bad site must not break anything upstream
        result.status = "error"
        result.errors.append(str(exc))
        result.duration = round(time.monotonic() - started, 3)
        logger.warning("website enrichment: crawl failed", extra={"company_id": company_id, "error": str(exc)})
        return result

    homepage = pages[0] if pages else None
    result.status_code = homepage.status_code if homepage else None
    result.is_alive = bool(homepage and homepage.status_code and homepage.status_code < 400)

    website.status_code = result.status_code
    website.is_alive = result.is_alive
    website.checked_at = datetime.utcnow()

    result.pages_requested = len(pages)

    collected_phones: dict[str, tuple[str, str, float]] = {}  # normalized -> (raw, page_url, confidence)
    collected_emails: dict[str, tuple[str, float]] = {}  # normalized -> (page_url, confidence)
    collected_socials: dict[tuple[str, str], str] = {}  # (platform, url) -> page_url

    for page in pages:
        if page.error or not page.html:
            result.pages_failed += 1
            if page.error:
                result.errors.append(f"{page.url}: {page.error}")
            continue

        result.pages_successful += 1
        phones, emails, socials = extract_contacts(page.html, page.url)

        for p in phones:
            normalized = normalize_phone(p.raw)
            if not normalized:
                continue
            existing = collected_phones.get(normalized)
            if existing is None or p.confidence > existing[2]:
                collected_phones[normalized] = (p.raw, p.page_url, p.confidence)

        for e in emails:
            normalized = normalize_email(e.raw)
            if not normalized:
                continue
            existing = collected_emails.get(normalized)
            if existing is None or e.confidence > existing[1]:
                collected_emails[normalized] = (e.page_url, e.confidence)

        for s in socials:
            key = (s.platform, s.url)
            collected_socials.setdefault(key, s.page_url)

    result.phones = list(collected_phones.keys())
    result.emails = list(collected_emails.keys())
    result.social_links = [url for (_, url) in collected_socials.keys()]

    for normalized, (raw, page_url, confidence) in collected_phones.items():
        source = _get_or_create_website_source(db, page_url)
        if _persist_phone(db, company_id, normalized, raw, source.id, confidence):
            result.phones_added += 1

    for normalized, (page_url, confidence) in collected_emails.items():
        source = _get_or_create_website_source(db, page_url)
        if _persist_email(db, company_id, normalized, source.id, confidence):
            result.emails_added += 1

    for (platform, url), page_url in collected_socials.items():
        source = _get_or_create_website_source(db, page_url)
        if _persist_social(db, company_id, platform, url, source.id):
            result.socials_added += 1

    result.duration = round(time.monotonic() - started, 3)
    return result


async def enrich_companies_websites(
    db: Session, company_ids: list[str], crawler: WebsiteCrawler | None = None
) -> tuple[list[WebsiteEnrichmentResult], WebsiteBatchStats]:
    started = time.monotonic()
    stats = WebsiteBatchStats(received=len(company_ids))
    results: list[WebsiteEnrichmentResult] = []

    shared_crawler = crawler or WebsiteCrawler()

    for company_id in company_ids:
        try:
            with db.begin_nested():
                result = await enrich_company_website(db, company_id, crawler=shared_crawler)

            results.append(result)

            if result.status == "skipped_no_website":
                stats.skipped_no_website += 1
                continue

            stats.with_website += 1

            if result.status == "error":
                stats.failed += 1
                continue

            stats.attempted += 1
            if result.is_alive:
                stats.alive += 1
            else:
                stats.dead += 1

            stats.pages_requested += result.pages_requested
            stats.pages_successful += result.pages_successful

            stats.phones_found += len(result.phones)
            stats.phones_added += result.phones_added
            stats.emails_found += len(result.emails)
            stats.emails_added += result.emails_added
            stats.socials_found += len(result.social_links)
            stats.socials_added += result.socials_added

        except Exception as exc:  # noqa: BLE001 - isolate one bad company
            stats.failed += 1
            stats.errors.append(str(exc))
            logger.warning(
                "website enrichment batch: failed to enrich company",
                extra={"company_id": company_id, "error": str(exc)},
            )

    db.commit()
    stats.duration = time.monotonic() - started
    return results, stats
