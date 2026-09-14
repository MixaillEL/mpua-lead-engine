"""Builds the client-facing export dataset (list[ExportRow]) for one
JobRun, scoped strictly through `job_run_companies` — never "all Company
rows in the DB". Batch-loads every related table once (no N+1 per
Company) and assembles rows in Python.
"""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.address import Address
from app.models.company import Company
from app.models.company_email import CompanyEmail
from app.models.company_phone import CompanyPhone
from app.models.company_source import CompanySource
from app.models.company_website import CompanyWebsite
from app.models.job_run_company import JobRunCompany
from app.models.social_link import SocialLink
from app.models.source import Source
from exporters.models import ExportRow

SOCIAL_COLUMNS = {
    "facebook": "facebook",
    "instagram": "instagram",
    "telegram": "telegram",
    "linkedin": "linkedin",
    "youtube": "youtube",
    "tiktok": "tiktok",
}


def _top_n_phones(rows: list[CompanyPhone], n: int = 3) -> list[str]:
    ordered = sorted(
        rows,
        key=lambda r: (
            -(r.confidence if r.confidence is not None else 0.0),
            -(r.observed_at.timestamp() if r.observed_at else 0.0),
            r.phone_normalized or "",
        ),
    )
    seen: list[str] = []
    for r in ordered:
        if r.phone_normalized and r.phone_normalized not in seen:
            seen.append(r.phone_normalized)
        if len(seen) >= n:
            break
    return seen


def _top_n_emails(rows: list[CompanyEmail], n: int = 3) -> list[str]:
    ordered = sorted(
        rows,
        key=lambda r: (
            -(r.confidence if r.confidence is not None else 0.0),
            -(r.observed_at.timestamp() if r.observed_at else 0.0),
            r.email or "",
        ),
    )
    seen: list[str] = []
    for r in ordered:
        if r.email and r.email not in seen:
            seen.append(r.email)
        if len(seen) >= n:
            break
    return seen


def _primary_website(rows: list[CompanyWebsite]) -> str | None:
    if not rows:
        return None

    def sort_key(r: CompanyWebsite):
        alive_rank = 0 if r.is_alive else 1
        checked_rank = -(r.checked_at.timestamp()) if r.checked_at else 0.0
        return (alive_rank, checked_rank, r.id)

    best = sorted(rows, key=sort_key)[0]
    return best.url or (f"https://{best.domain}" if best.domain else None)


def _address_completeness(a: Address) -> int:
    return sum(1 for v in (a.street, a.city, a.postal_code, a.raw_address) if v)


def _primary_address(rows: list[Address]) -> str | None:
    if not rows:
        return None

    best = sorted(rows, key=lambda a: (-_address_completeness(a), a.id))[0]

    parts = [best.street, best.city, best.postal_code]
    parts = [p for p in parts if p]
    if parts:
        return ", ".join(parts)
    return best.raw_address


def get_job_run_company_ids(db: Session, job_run_id: str) -> list[str]:
    return list(
        db.scalars(
            select(JobRunCompany.company_id).where(JobRunCompany.job_run_id == job_run_id)
        ).all()
    )


def build_export_rows(db: Session, job_run_id: str) -> list[ExportRow]:
    company_ids = get_job_run_company_ids(db, job_run_id)
    if not company_ids:
        return []

    companies = db.scalars(
        select(Company)
        .where(Company.id.in_(company_ids))
        .order_by(Company.country, Company.region, Company.city, Company.normalized_name, Company.id)
    ).all()

    phones_by_company: dict[str, list[CompanyPhone]] = defaultdict(list)
    for row in db.scalars(select(CompanyPhone).where(CompanyPhone.company_id.in_(company_ids))):
        phones_by_company[row.company_id].append(row)

    emails_by_company: dict[str, list[CompanyEmail]] = defaultdict(list)
    for row in db.scalars(select(CompanyEmail).where(CompanyEmail.company_id.in_(company_ids))):
        emails_by_company[row.company_id].append(row)

    websites_by_company: dict[str, list[CompanyWebsite]] = defaultdict(list)
    for row in db.scalars(select(CompanyWebsite).where(CompanyWebsite.company_id.in_(company_ids))):
        websites_by_company[row.company_id].append(row)

    addresses_by_company: dict[str, list[Address]] = defaultdict(list)
    for row in db.scalars(select(Address).where(Address.company_id.in_(company_ids))):
        addresses_by_company[row.company_id].append(row)

    socials_by_company: dict[str, dict[str, list[SocialLink]]] = defaultdict(lambda: defaultdict(list))
    for row in db.scalars(select(SocialLink).where(SocialLink.company_id.in_(company_ids))):
        socials_by_company[row.company_id][row.platform.value].append(row)

    source_types_by_company: dict[str, set[str]] = defaultdict(set)
    source_urls_by_company: dict[str, list[str]] = defaultdict(list)
    for company_id, source_type, source_url in db.execute(
        select(CompanySource.company_id, Source.source_type, Source.source_url)
        .join(Source, Source.id == CompanySource.source_id)
        .where(CompanySource.company_id.in_(company_ids))
        .order_by(Source.collected_at)
    ):
        source_types_by_company[company_id].add(source_type.value)
        if source_url and source_url not in source_urls_by_company[company_id]:
            source_urls_by_company[company_id].append(source_url)

    rows: list[ExportRow] = []
    for company in companies:
        phones = _top_n_phones(phones_by_company.get(company.id, []))
        emails = _top_n_emails(emails_by_company.get(company.id, []))
        socials = socials_by_company.get(company.id, {})

        source_types = sorted(source_types_by_company.get(company.id, set()))

        rows.append(
            ExportRow(
                company_id=company.id,
                company_name=company.canonical_name,
                category=company.category,
                country=company.country,
                region=company.region,
                city=company.city,
                address=_primary_address(addresses_by_company.get(company.id, [])),
                phone_1=phones[0] if len(phones) > 0 else None,
                phone_2=phones[1] if len(phones) > 1 else None,
                phone_3=phones[2] if len(phones) > 2 else None,
                email_1=emails[0] if len(emails) > 0 else None,
                email_2=emails[1] if len(emails) > 1 else None,
                email_3=emails[2] if len(emails) > 2 else None,
                website=_primary_website(websites_by_company.get(company.id, [])),
                facebook=socials["facebook"][0].url if socials.get("facebook") else None,
                instagram=socials["instagram"][0].url if socials.get("instagram") else None,
                telegram=socials["telegram"][0].url if socials.get("telegram") else None,
                linkedin=socials["linkedin"][0].url if socials.get("linkedin") else None,
                youtube=socials["youtube"][0].url if socials.get("youtube") else None,
                tiktok=socials["tiktok"][0].url if socials.get("tiktok") else None,
                rating=company.rating,
                reviews=company.reviews_count,
                source_types="; ".join(source_types) if source_types else None,
                source_urls="; ".join(source_urls_by_company.get(company.id, [])) or None,
                first_seen=company.first_seen_at,
                last_seen=company.last_seen_at,
            )
        )

    return rows
