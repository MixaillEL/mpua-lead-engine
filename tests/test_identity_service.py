import pytest
from sqlalchemy import select

from app.models.company import Company
from app.models.company_email import CompanyEmail
from app.models.company_phone import CompanyPhone
from app.models.company_source import CompanySource
from app.models.company_website import CompanyWebsite
from app.models.source import Source, SourceType
from processing.identity.models import Decision
from processing.identity.service import resolve_and_persist_candidate, resolve_candidates
from processing.normalization.models import NormalizedCandidate


def _cleanup_companies(db, company_ids):
    for company_id in company_ids:
        company = db.get(Company, company_id)
        if company is not None:
            db.delete(company)
    db.commit()


def _cleanup_sources(db, source_ids):
    for source_id in source_ids:
        source = db.get(Source, source_id)
        if source is not None:
            db.delete(source)
    db.commit()


def _candidate(**overrides) -> NormalizedCandidate:
    defaults = dict(
        external_id=None,
        canonical_name="ТОВ Альфа",
        normalized_name="альфа",
        category="HVAC",
        country="UA",
        region="Dnipro",
        city="Dnipro",
        normalized_city="dnipro",
        raw_address=None,
        normalized_address=None,
        phone_raw="0501111111",
        phone_normalized="+380501111111",
        email_raw=None,
        email_normalized=None,
        website_raw=None,
        website_url=None,
        website_domain=None,
        rating=None,
        reviews_count=None,
        source_type=SourceType.manual,
        source_url=None,
        raw_payload=None,
    )
    defaults.update(overrides)
    return NormalizedCandidate(**defaults)


def _make_source(db, source_type=SourceType.openstreetmap, external_id="osm:node:1") -> Source:
    source = Source(source_type=source_type, external_id=external_id)
    db.add(source)
    db.commit()
    return source


@pytest.mark.asyncio
async def test_new_candidate_creates_company(committing_db_session):
    db = committing_db_session
    candidate = _candidate(canonical_name="ТОВ Нова Компанія", normalized_name="нова компанія")

    result, added = resolve_and_persist_candidate(db, candidate, source_id=None)
    db.commit()

    try:
        assert result.decision == Decision.NEW
        assert result.created is True
        assert result.company_id is not None

        company = db.get(Company, result.company_id)
        assert company.canonical_name == "ТОВ Нова Компанія"
    finally:
        _cleanup_companies(db, [result.company_id])


@pytest.mark.asyncio
async def test_same_phone_matches_existing_company(committing_db_session):
    db = committing_db_session

    a = _candidate(canonical_name="ТОВ Альфа", normalized_name="альфа", phone_normalized="+380501111111")
    b = _candidate(
        canonical_name="Альфа Сервіс", normalized_name="альфа сервіс", phone_normalized="+380501111111"
    )

    result_a, _ = resolve_and_persist_candidate(db, a, source_id=None)
    db.commit()
    result_b, _ = resolve_and_persist_candidate(db, b, source_id=None)
    db.commit()

    try:
        assert result_a.decision == Decision.NEW
        assert result_b.decision == Decision.MATCH
        assert result_b.company_id == result_a.company_id

        companies = db.scalars(select(Company).where(Company.id == result_a.company_id)).all()
        assert len(companies) == 1
    finally:
        _cleanup_companies(db, [result_a.company_id])


@pytest.mark.asyncio
async def test_same_domain_matches_existing_company(committing_db_session):
    db = committing_db_session

    a = _candidate(
        canonical_name="Example HVAC",
        normalized_name="example hvac",
        phone_normalized=None,
        website_domain="example.com",
    )
    b = _candidate(
        canonical_name="Example Climate",
        normalized_name="example climate",
        phone_normalized=None,
        website_domain="example.com",
    )

    result_a, _ = resolve_and_persist_candidate(db, a, source_id=None)
    db.commit()
    result_b, _ = resolve_and_persist_candidate(db, b, source_id=None)
    db.commit()

    try:
        assert result_a.decision == Decision.NEW
        assert result_b.decision == Decision.MATCH
        assert result_b.company_id == result_a.company_id
    finally:
        _cleanup_companies(db, [result_a.company_id])


@pytest.mark.asyncio
async def test_same_source_external_id_processed_twice_yields_one_company(committing_db_session):
    db = committing_db_session

    source1 = _make_source(db, external_id="osm:node:123")
    source2 = _make_source(db, external_id="osm:node:123")

    candidate = _candidate(
        external_id="osm:node:123",
        canonical_name="Dental Studio",
        normalized_name="dental studio",
        phone_normalized=None,
        source_type=SourceType.openstreetmap,
    )

    result_1, _ = resolve_and_persist_candidate(db, candidate, source_id=source1.id)
    db.commit()
    result_2, _ = resolve_and_persist_candidate(db, candidate, source_id=source2.id)
    db.commit()

    try:
        assert result_1.decision == Decision.NEW
        assert result_2.decision == Decision.MATCH
        assert result_2.company_id == result_1.company_id

        links = db.scalars(
            select(CompanySource).where(CompanySource.company_id == result_1.company_id)
        ).all()
        assert len(links) == 2  # both Source rows recorded as provenance
    finally:
        _cleanup_companies(db, [result_1.company_id])
        _cleanup_sources(db, [source1.id, source2.id])


@pytest.mark.asyncio
async def test_name_city_only_is_review_and_not_persisted(committing_db_session):
    db = committing_db_session

    a = _candidate(
        canonical_name="Стоматологія",
        normalized_name="стоматологія",
        normalized_city="дніпро",
        phone_normalized=None,
    )
    b = _candidate(
        canonical_name="Стоматологія",
        normalized_name="стоматологія",
        normalized_city="дніпро",
        phone_normalized=None,
    )

    result_a, _ = resolve_and_persist_candidate(db, a, source_id=None)
    db.commit()
    result_b, _ = resolve_and_persist_candidate(db, b, source_id=None)
    db.commit()

    try:
        assert result_a.decision == Decision.NEW
        assert result_b.decision == Decision.REVIEW
        assert result_b.created is False
        assert result_b.merged is False

        companies = db.scalars(
            select(Company).where(
                Company.normalized_name == "стоматологія", Company.normalized_city == "дніпро"
            )
        ).all()
        assert len(companies) == 1  # review candidate was NOT persisted as a 2nd company
    finally:
        _cleanup_companies(db, [result_a.company_id])


@pytest.mark.asyncio
async def test_same_name_different_city_creates_two_companies(committing_db_session):
    db = committing_db_session

    a = _candidate(
        canonical_name="Авто Плюс",
        normalized_name="авто плюс",
        normalized_city="київ",
        phone_normalized=None,
    )
    b = _candidate(
        canonical_name="Авто Плюс",
        normalized_name="авто плюс",
        normalized_city="львів",
        phone_normalized=None,
    )

    result_a, _ = resolve_and_persist_candidate(db, a, source_id=None)
    db.commit()
    result_b, _ = resolve_and_persist_candidate(db, b, source_id=None)
    db.commit()

    try:
        assert result_a.decision == Decision.NEW
        assert result_b.decision == Decision.NEW
        assert result_a.company_id != result_b.company_id
    finally:
        _cleanup_companies(db, [result_a.company_id, result_b.company_id])


@pytest.mark.asyncio
async def test_name_and_address_matches(committing_db_session):
    db = committing_db_session

    a = _candidate(
        canonical_name="Клімат Сервіс",
        normalized_name="клімат сервіс",
        phone_normalized=None,
        raw_address="вул. Шевченка, 10",
        normalized_address="вул. шевченка 10",
    )
    b = _candidate(
        canonical_name="Клімат Сервіс",
        normalized_name="клімат сервіс",
        phone_normalized=None,
        raw_address="вул. Шевченка, 10",
        normalized_address="вул. шевченка 10",
    )

    result_a, _ = resolve_and_persist_candidate(db, a, source_id=None)
    db.commit()
    result_b, _ = resolve_and_persist_candidate(db, b, source_id=None)
    db.commit()

    try:
        assert result_b.decision == Decision.MATCH
        assert result_b.company_id == result_a.company_id
    finally:
        _cleanup_companies(db, [result_a.company_id])


@pytest.mark.asyncio
async def test_idempotent_phone_email_website_not_duplicated(committing_db_session):
    db = committing_db_session

    candidate = _candidate(
        canonical_name="Idempotent Co",
        normalized_name="idempotent co",
        phone_normalized="+380502222222",
        email_normalized="info@idem.example.com",
        website_domain="idem.example.com",
        website_url="https://idem.example.com/",
    )

    result_1, _ = resolve_and_persist_candidate(db, candidate, source_id=None)
    db.commit()
    result_2, _ = resolve_and_persist_candidate(db, candidate, source_id=None)
    db.commit()

    try:
        assert result_1.decision == Decision.NEW
        assert result_2.decision == Decision.MATCH
        assert result_1.company_id == result_2.company_id

        phones = db.scalars(
            select(CompanyPhone).where(CompanyPhone.company_id == result_1.company_id)
        ).all()
        emails = db.scalars(
            select(CompanyEmail).where(CompanyEmail.company_id == result_1.company_id)
        ).all()
        websites = db.scalars(
            select(CompanyWebsite).where(CompanyWebsite.company_id == result_1.company_id)
        ).all()

        assert len(phones) == 1
        assert len(emails) == 1
        assert len(websites) == 1
    finally:
        _cleanup_companies(db, [result_1.company_id])


@pytest.mark.asyncio
async def test_merge_preserves_existing_data_and_adds_new(committing_db_session):
    db = committing_db_session

    existing = _candidate(
        canonical_name="Merge Co",
        normalized_name="merge co",
        phone_normalized="+380503333333",
        website_domain="merge.example.com",
        website_url="https://merge.example.com/",
        email_normalized=None,
    )
    new_data = _candidate(
        canonical_name="Merge Co Alt Name",
        normalized_name="merge co",
        phone_normalized="+380503333333",  # same phone -> MATCH
        website_domain=None,
        email_normalized="sales@merge.example.com",  # new contact to add
    )

    result_1, _ = resolve_and_persist_candidate(db, existing, source_id=None)
    db.commit()
    result_2, _ = resolve_and_persist_candidate(db, new_data, source_id=None)
    db.commit()

    try:
        assert result_2.decision == Decision.MATCH
        company = db.get(Company, result_1.company_id)
        # existing canonical_name wins (conflict policy: don't overwrite)
        assert company.canonical_name == "Merge Co"

        websites = db.scalars(
            select(CompanyWebsite).where(CompanyWebsite.company_id == result_1.company_id)
        ).all()
        emails = db.scalars(
            select(CompanyEmail).where(CompanyEmail.company_id == result_1.company_id)
        ).all()

        assert len(websites) == 1  # preserved from the first candidate
        assert len(emails) == 1  # added from the second candidate
        assert emails[0].email == "sales@merge.example.com"
    finally:
        _cleanup_companies(db, [result_1.company_id])


@pytest.mark.asyncio
async def test_batch_isolates_one_bad_candidate(committing_db_session, monkeypatch):
    db = committing_db_session

    good = _candidate(
        canonical_name="Good Co", normalized_name="good co", phone_normalized="+380504444444"
    )
    bad = _candidate(
        canonical_name="Bad Co", normalized_name="bad co", phone_normalized="+380505555555"
    )

    import processing.identity.service as service_module

    original = service_module.resolve_and_persist_candidate

    def flaky(db_arg, candidate, source_id=None):
        if candidate.canonical_name == "Bad Co":
            raise RuntimeError("simulated failure")
        return original(db_arg, candidate, source_id)

    monkeypatch.setattr(service_module, "resolve_and_persist_candidate", flaky)

    results, stats = service_module.resolve_candidates(db, [(good, None), (bad, None)])

    created_ids = [r.company_id for r in results if r.company_id]
    try:
        assert stats.received == 2
        assert stats.failed == 1
        assert stats.new == 1
        assert len(results) == 1
    finally:
        _cleanup_companies(db, created_ids)
