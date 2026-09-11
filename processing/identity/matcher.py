"""Candidate retrieval + scoring. Loads only companies reachable through an
indexed field (phone/domain/email/name+city/address/external_id) — never a
full Company table scan.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.address import Address
from app.models.company import Company
from app.models.company_email import CompanyEmail
from app.models.company_phone import CompanyPhone
from app.models.company_website import CompanyWebsite
from app.models.company_source import CompanySource
from app.models.source import Source
from processing.identity.signals import MatchCandidate, evaluate_signals, is_shared_domain
from processing.normalization.models import NormalizedCandidate


def _candidate_company_ids(
    db: Session,
    candidate: NormalizedCandidate,
    source_type: str | None,
    external_id: str | None,
) -> set[str]:
    company_ids: set[str] = set()

    if candidate.phone_normalized:
        company_ids.update(
            db.scalars(
                select(CompanyPhone.company_id).where(
                    CompanyPhone.phone_normalized == candidate.phone_normalized
                )
            ).all()
        )

    if candidate.website_domain and not is_shared_domain(candidate.website_domain):
        company_ids.update(
            db.scalars(
                select(CompanyWebsite.company_id).where(
                    CompanyWebsite.domain == candidate.website_domain
                )
            ).all()
        )

    if candidate.email_normalized:
        company_ids.update(
            db.scalars(
                select(CompanyEmail.company_id).where(CompanyEmail.email == candidate.email_normalized)
            ).all()
        )

    if candidate.normalized_name and candidate.normalized_city:
        company_ids.update(
            db.scalars(
                select(Company.id).where(
                    Company.normalized_name == candidate.normalized_name,
                    Company.normalized_city == candidate.normalized_city,
                )
            ).all()
        )

    if candidate.normalized_address:
        company_ids.update(
            db.scalars(
                select(Address.company_id).where(
                    Address.normalized_address == candidate.normalized_address
                )
            ).all()
        )

    if source_type and external_id:
        company_ids.update(
            db.scalars(
                select(CompanySource.company_id)
                .join(Source, Source.id == CompanySource.source_id)
                .where(Source.source_type == source_type, Source.external_id == external_id)
            ).all()
        )

    return company_ids


def _build_match_candidates(db: Session, company_ids: set[str]) -> list[MatchCandidate]:
    if not company_ids:
        return []

    companies = db.scalars(select(Company).where(Company.id.in_(company_ids))).all()

    phones_by_company: dict[str, set[str]] = {}
    for company_id, phone in db.execute(
        select(CompanyPhone.company_id, CompanyPhone.phone_normalized).where(
            CompanyPhone.company_id.in_(company_ids), CompanyPhone.phone_normalized.is_not(None)
        )
    ):
        phones_by_company.setdefault(company_id, set()).add(phone)

    emails_by_company: dict[str, set[str]] = {}
    for company_id, email in db.execute(
        select(CompanyEmail.company_id, CompanyEmail.email).where(
            CompanyEmail.company_id.in_(company_ids)
        )
    ):
        emails_by_company.setdefault(company_id, set()).add(email)

    domains_by_company: dict[str, set[str]] = {}
    for company_id, domain in db.execute(
        select(CompanyWebsite.company_id, CompanyWebsite.domain).where(
            CompanyWebsite.company_id.in_(company_ids), CompanyWebsite.domain.is_not(None)
        )
    ):
        domains_by_company.setdefault(company_id, set()).add(domain)

    addresses_by_company: dict[str, set[str]] = {}
    for company_id, normalized_address in db.execute(
        select(Address.company_id, Address.normalized_address).where(
            Address.company_id.in_(company_ids), Address.normalized_address.is_not(None)
        )
    ):
        addresses_by_company.setdefault(company_id, set()).add(normalized_address)

    external_ids_by_company: dict[str, set[tuple[str, str]]] = {}
    for company_id, source_type, external_id in db.execute(
        select(CompanySource.company_id, Source.source_type, Source.external_id)
        .join(Source, Source.id == CompanySource.source_id)
        .where(CompanySource.company_id.in_(company_ids), Source.external_id.is_not(None))
    ):
        external_ids_by_company.setdefault(company_id, set()).add((source_type, external_id))

    return [
        MatchCandidate(
            company_id=company.id,
            normalized_name=company.normalized_name,
            normalized_city=company.normalized_city,
            phones=frozenset(phones_by_company.get(company.id, set())),
            emails=frozenset(emails_by_company.get(company.id, set())),
            domains=frozenset(domains_by_company.get(company.id, set())),
            normalized_addresses=frozenset(addresses_by_company.get(company.id, set())),
            external_ids=frozenset(external_ids_by_company.get(company.id, set())),
        )
        for company in companies
    ]


def find_scored_matches(
    db: Session,
    candidate: NormalizedCandidate,
    source_type: str | None = None,
    external_id: str | None = None,
) -> list[tuple[MatchCandidate, int, list[str]]]:
    """Returns (match_candidate, score, signals) tuples, best score first."""

    company_ids = _candidate_company_ids(db, candidate, source_type, external_id)
    match_candidates = _build_match_candidates(db, company_ids)

    scored = []
    for match in match_candidates:
        score, signals = evaluate_signals(
            normalized_name=candidate.normalized_name,
            normalized_city=candidate.normalized_city,
            normalized_address=candidate.normalized_address,
            phone_normalized=candidate.phone_normalized,
            email_normalized=candidate.email_normalized,
            website_domain=candidate.website_domain,
            source_type=source_type,
            external_id=external_id,
            match=match,
        )
        if score > 0:
            scored.append((match, score, signals))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored
