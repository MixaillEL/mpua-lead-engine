from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.models.company import Company
from app.models.company_email import CompanyEmail
from app.models.company_phone import CompanyPhone
from app.models.company_website import CompanyWebsite
from app.models.social_link import SocialLink
from app.models.source import Source, SourceType
from enrichment.website.crawler import WebsiteCrawler
from enrichment.website.service import enrich_companies_websites, enrich_company_website

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _make_company(db, **overrides) -> Company:
    defaults = dict(canonical_name="Example HVAC", normalized_name="example hvac")
    defaults.update(overrides)
    company = Company(**defaults)
    db.add(company)
    db.commit()
    return company


def _cleanup(db, company_ids):
    for company_id in company_ids:
        company = db.get(Company, company_id)
        if company is not None:
            db.delete(company)
    db.commit()


def _cleanup_sources_for(db, source_urls):
    for url in source_urls:
        source = db.scalar(select(Source).where(Source.source_url == url))
        if source is not None:
            db.delete(source)
    db.commit()


def _complete_site_handler(request: httpx.Request) -> httpx.Response:
    html_a = _load("website_a_complete.html")
    if request.url.path == "/":
        return httpx.Response(200, content=html_a.encode(), headers={"content-type": "text/html"})
    return httpx.Response(200, content=b"<html><body>ok</body></html>", headers={"content-type": "text/html"})


@pytest.mark.asyncio
async def test_skipped_when_no_website(committing_db_session):
    db = committing_db_session
    company = _make_company(db, canonical_name="No Website Co", normalized_name="no website co")

    try:
        result = await enrich_company_website(db, company.id)
        assert result.status == "skipped_no_website"
    finally:
        _cleanup(db, [company.id])


@pytest.mark.asyncio
async def test_enrich_adds_phone_email_social(committing_db_session):
    db = committing_db_session
    company = _make_company(db)
    website = CompanyWebsite(company_id=company.id, url="https://example.com/", domain="example.com")
    db.add(website)
    db.commit()

    crawler = WebsiteCrawler(client=_client(_complete_site_handler))

    try:
        result = await enrich_company_website(db, company.id, crawler=crawler)

        assert result.status == "ok"
        assert result.is_alive is True
        assert result.phones_added >= 1
        assert result.emails_added >= 1
        assert result.socials_added >= 1

        phones = db.scalars(select(CompanyPhone).where(CompanyPhone.company_id == company.id)).all()
        emails = db.scalars(select(CompanyEmail).where(CompanyEmail.company_id == company.id)).all()
        socials = db.scalars(select(SocialLink).where(SocialLink.company_id == company.id)).all()

        assert len(phones) >= 1
        assert len(emails) >= 1
        assert len(socials) >= 1
        assert phones[0].phone_normalized == "+380501234567"
        assert phones[0].source_id is not None

        # provenance: phone's Source must be source_type=website with a URL
        source = db.get(Source, phones[0].source_id)
        assert source.source_type == SourceType.website
        assert source.source_url is not None
    finally:
        db.refresh(website)
        source_ids = [
            r[0]
            for r in db.execute(
                select(CompanyPhone.source_id).where(CompanyPhone.company_id == company.id)
            )
        ]
        _cleanup(db, [company.id])
        for source_id in source_ids:
            if source_id:
                source = db.get(Source, source_id)
                if source is not None:
                    db.delete(source)
        db.commit()


@pytest.mark.asyncio
async def test_idempotent_second_run_does_not_duplicate(committing_db_session):
    db = committing_db_session
    company = _make_company(db)
    website = CompanyWebsite(company_id=company.id, url="https://example.com/", domain="example.com")
    db.add(website)
    db.commit()

    try:
        crawler_1 = WebsiteCrawler(client=_client(_complete_site_handler))
        result_1 = await enrich_company_website(db, company.id, crawler=crawler_1)

        crawler_2 = WebsiteCrawler(client=_client(_complete_site_handler))
        result_2 = await enrich_company_website(db, company.id, crawler=crawler_2)

        assert result_1.phones_added >= 1
        assert result_2.phones_added == 0
        assert result_2.emails_added == 0
        assert result_2.socials_added == 0

        phones = db.scalars(select(CompanyPhone).where(CompanyPhone.company_id == company.id)).all()
        assert len(phones) == len({p.phone_normalized for p in phones})
    finally:
        source_ids = [
            r[0]
            for r in db.execute(
                select(CompanyPhone.source_id).where(CompanyPhone.company_id == company.id)
            )
        ]
        _cleanup(db, [company.id])
        for source_id in source_ids:
            if source_id:
                source = db.get(Source, source_id)
                if source is not None:
                    db.delete(source)
        db.commit()


@pytest.mark.asyncio
async def test_shared_domain_website_is_never_crawled(committing_db_session):
    db = committing_db_session
    company = _make_company(db, canonical_name="FB Only Co", normalized_name="fb only co")
    website = CompanyWebsite(
        company_id=company.id, url="https://facebook.com/fbonlyco", domain="facebook.com"
    )
    db.add(website)
    db.commit()

    try:
        result = await enrich_company_website(db, company.id)
        assert result.status == "skipped_no_website"
    finally:
        _cleanup(db, [company.id])


@pytest.mark.asyncio
async def test_batch_isolates_one_bad_company(committing_db_session):
    db = committing_db_session

    good = _make_company(db, canonical_name="Good Co", normalized_name="good co")
    good_site = CompanyWebsite(company_id=good.id, url="https://example.com/", domain="example.com")
    db.add(good_site)

    bad = _make_company(db, canonical_name="Bad Co", normalized_name="bad co")
    bad_site = CompanyWebsite(company_id=bad.id, url="https://timeout.example/", domain="timeout.example")
    db.add(bad_site)
    db.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if "timeout.example" in str(request.url):
            raise httpx.ConnectError("simulated DNS failure", request=request)
        return _complete_site_handler(request)

    shared_client = _client(handler)
    crawler = WebsiteCrawler(client=shared_client)

    try:
        results, stats = await enrich_companies_websites(db, [good.id, bad.id], crawler=crawler)

        assert stats.received == 2
        assert stats.with_website == 2
        assert stats.alive == 1
        assert stats.dead == 1  # timeout site marked dead, not a hard failure
        assert len(results) == 2
    finally:
        source_ids = [
            r[0]
            for r in db.execute(
                select(CompanyPhone.source_id).where(CompanyPhone.company_id == good.id)
            )
        ]
        _cleanup(db, [good.id, bad.id])
        for source_id in source_ids:
            if source_id:
                source = db.get(Source, source_id)
                if source is not None:
                    db.delete(source)
        db.commit()
