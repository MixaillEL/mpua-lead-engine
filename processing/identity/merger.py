"""Company create/merge persistence. All contact writes are idempotent
(get-or-create against the unique constraints added in MLE-005) so
reprocessing the same NormalizedCandidate never creates duplicate rows.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.address import Address
from app.models.company import Company
from app.models.company_email import CompanyEmail
from app.models.company_phone import CompanyPhone
from app.models.company_source import CompanySource
from app.models.company_website import CompanyWebsite
from processing.normalization.models import NormalizedCandidate


def create_company(
    db: Session, candidate: NormalizedCandidate, source_id: str | None
) -> tuple[Company, int]:
    now = datetime.utcnow()

    company = Company(
        canonical_name=candidate.canonical_name,
        normalized_name=candidate.normalized_name,
        category=candidate.category,
        description=candidate.description,
        country=candidate.country,
        region=candidate.region,
        city=candidate.city,
        normalized_city=candidate.normalized_city,
        rating=candidate.rating,
        reviews_count=candidate.reviews_count,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(company)
    db.flush()

    added = _attach_contacts(db, company.id, candidate, source_id)
    if source_id:
        _link_source(db, company.id, source_id)

    return company, added


def merge_into_company(
    db: Session, company_id: str, candidate: NormalizedCandidate, source_id: str | None
) -> tuple[Company, int]:
    company = db.get(Company, company_id)
    if company is None:
        raise ValueError(f"Company {company_id} not found")

    # Conflict policy (MLE-005 v0.1): existing canonical_name/rating/reviews
    # win; new values don't overwrite. Only last_seen_at advances. The new
    # candidate's raw values still survive via RawRecord/Source provenance.
    company.last_seen_at = datetime.utcnow()

    added = _attach_contacts(db, company.id, candidate, source_id)
    if source_id:
        _link_source(db, company.id, source_id)

    return company, added


def _attach_contacts(
    db: Session, company_id: str, candidate: NormalizedCandidate, source_id: str | None
) -> int:
    now = datetime.utcnow()
    added = 0

    if candidate.phone_normalized:
        existing = db.scalar(
            select(CompanyPhone).where(
                CompanyPhone.company_id == company_id,
                CompanyPhone.phone_normalized == candidate.phone_normalized,
            )
        )
        if existing is None:
            db.add(
                CompanyPhone(
                    company_id=company_id,
                    phone_raw=candidate.phone_raw or candidate.phone_normalized,
                    phone_normalized=candidate.phone_normalized,
                    source_id=source_id,
                    observed_at=now,
                )
            )
            added += 1

    if candidate.email_normalized:
        existing = db.scalar(
            select(CompanyEmail).where(
                CompanyEmail.company_id == company_id,
                CompanyEmail.email == candidate.email_normalized,
            )
        )
        if existing is None:
            domain = candidate.email_normalized.rsplit("@", 1)[-1]
            db.add(
                CompanyEmail(
                    company_id=company_id,
                    email=candidate.email_normalized,
                    domain=domain,
                    source_id=source_id,
                    observed_at=now,
                )
            )
            added += 1

    if candidate.website_domain:
        existing = db.scalar(
            select(CompanyWebsite).where(
                CompanyWebsite.company_id == company_id,
                CompanyWebsite.domain == candidate.website_domain,
            )
        )
        if existing is None:
            db.add(
                CompanyWebsite(
                    company_id=company_id,
                    url=candidate.website_url or candidate.website_raw or f"https://{candidate.website_domain}",
                    domain=candidate.website_domain,
                    source_id=source_id,
                )
            )
            added += 1

    if candidate.normalized_address:
        existing = db.scalar(
            select(Address).where(
                Address.company_id == company_id,
                Address.normalized_address == candidate.normalized_address,
            )
        )
        if existing is None:
            db.add(
                Address(
                    company_id=company_id,
                    country=candidate.country,
                    region=candidate.region,
                    city=candidate.city,
                    raw_address=candidate.raw_address,
                    normalized_address=candidate.normalized_address,
                    source_id=source_id,
                )
            )
            added += 1

    db.flush()
    return added


def _link_source(db: Session, company_id: str, source_id: str) -> None:
    now = datetime.utcnow()

    existing = db.scalar(
        select(CompanySource).where(
            CompanySource.company_id == company_id, CompanySource.source_id == source_id
        )
    )
    if existing is None:
        db.add(
            CompanySource(
                company_id=company_id,
                source_id=source_id,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
    else:
        existing.last_seen_at = now

    db.flush()
