import pytest
from sqlalchemy import select

from app.models.address import Address
from app.models.company import Company
from app.models.company_email import CompanyEmail
from app.models.company_phone import CompanyPhone
from app.models.company_source import CompanySource
from app.models.company_website import CompanyWebsite
from app.models.job import Job, JobStatus
from app.models.job_run import JobRun, PipelineStage
from app.models.job_run_company import JobRunCompany, JobRunCompanyResolution
from app.models.social_link import SocialLink, SocialPlatform
from app.models.source import Source, SourceType
from exporters.dataset import build_export_rows


def _make_company(db, **overrides) -> Company:
    defaults = dict(canonical_name="Test Co", normalized_name="test co")
    defaults.update(overrides)
    company = Company(**defaults)
    db.add(company)
    db.commit()
    return company


def _make_job_run(db, **job_overrides) -> tuple[Job, JobRun]:
    job = Job(query="dentist", preset="dentist", regions=["Kyiv"], sources_config={"osm": True}, source_limits={"osm": 10})
    for k, v in job_overrides.items():
        setattr(job, k, v)
    db.add(job)
    db.commit()

    job_run = JobRun(job_id=job.id, status=JobStatus.completed, current_stage=PipelineStage.completed)
    db.add(job_run)
    db.commit()
    return job, job_run


def _link(db, job_run, company, resolution=JobRunCompanyResolution.new, source_count=1):
    link = JobRunCompany(job_run_id=job_run.id, company_id=company.id, resolution=resolution, source_count=source_count)
    db.add(link)
    db.commit()
    return link


def _cleanup(db, job_id, company_ids):
    for cid in company_ids:
        c = db.get(Company, cid)
        if c is not None:
            db.delete(c)
    db.commit()
    job = db.get(Job, job_id)
    if job is not None:
        db.delete(job)
    db.commit()


def test_job_run_with_one_company(committing_db_session):
    db = committing_db_session
    job, job_run = _make_job_run(db)
    company = _make_company(db, canonical_name="Alpha LLC", normalized_name="alpha llc", country="UA", city="Kyiv")
    _link(db, job_run, company)

    try:
        rows = build_export_rows(db, job_run.id)
        assert len(rows) == 1
        assert rows[0].company_name == "Alpha LLC"
        assert rows[0].city == "Kyiv"
    finally:
        _cleanup(db, job.id, [company.id])


def test_multiple_phones_collapse_into_three_columns(committing_db_session):
    db = committing_db_session
    job, job_run = _make_job_run(db)
    company = _make_company(db)
    _link(db, job_run, company)

    for i in range(5):
        db.add(CompanyPhone(company_id=company.id, phone_raw=f"05011122{i:02d}", phone_normalized=f"+38050111220{i}", confidence=1.0 - i * 0.1))
    db.commit()

    try:
        rows = build_export_rows(db, job_run.id)
        row = rows[0]
        assert row.phone_1 == "+380501112200"
        assert row.phone_2 == "+380501112201"
        assert row.phone_3 == "+380501112202"
    finally:
        _cleanup(db, job.id, [company.id])


def test_multiple_emails_collapse_into_three_columns(committing_db_session):
    db = committing_db_session
    job, job_run = _make_job_run(db)
    company = _make_company(db)
    _link(db, job_run, company)

    for i in range(4):
        db.add(CompanyEmail(company_id=company.id, email=f"user{i}@example.com", domain="example.com", confidence=1.0 - i * 0.1))
    db.commit()

    try:
        rows = build_export_rows(db, job_run.id)
        row = rows[0]
        assert row.email_1 == "user0@example.com"
        assert row.email_2 == "user1@example.com"
        assert row.email_3 == "user2@example.com"
    finally:
        _cleanup(db, job.id, [company.id])


def test_socials_map_to_correct_columns(committing_db_session):
    db = committing_db_session
    job, job_run = _make_job_run(db)
    company = _make_company(db)
    _link(db, job_run, company)

    db.add(SocialLink(company_id=company.id, platform=SocialPlatform.facebook, url="https://facebook.com/x", url_fingerprint="a" * 64))
    db.add(SocialLink(company_id=company.id, platform=SocialPlatform.instagram, url="https://instagram.com/x", url_fingerprint="b" * 64))
    db.commit()

    try:
        rows = build_export_rows(db, job_run.id)
        row = rows[0]
        assert row.facebook == "https://facebook.com/x"
        assert row.instagram == "https://instagram.com/x"
        assert row.telegram is None
    finally:
        _cleanup(db, job.id, [company.id])


def test_source_types_aggregate(committing_db_session):
    db = committing_db_session
    job, job_run = _make_job_run(db)
    company = _make_company(db)
    _link(db, job_run, company)

    s1 = Source(source_type=SourceType.openstreetmap, source_url="https://osm.example/1")
    s2 = Source(source_type=SourceType.web_search, source_url="https://tavily.example/2")
    db.add_all([s1, s2])
    db.commit()
    db.add(CompanySource(company_id=company.id, source_id=s1.id))
    db.add(CompanySource(company_id=company.id, source_id=s2.id))
    db.commit()

    try:
        rows = build_export_rows(db, job_run.id)
        row = rows[0]
        assert "openstreetmap" in row.source_types
        assert "web_search" in row.source_types
    finally:
        _cleanup(db, job.id, [company.id])
        for s in (s1, s2):
            src = db.get(Source, s.id)
            if src is not None:
                db.delete(src)
        db.commit()


def test_source_urls_aggregate(committing_db_session):
    db = committing_db_session
    job, job_run = _make_job_run(db)
    company = _make_company(db)
    _link(db, job_run, company)

    s1 = Source(source_type=SourceType.openstreetmap, source_url="https://osm.example/1")
    db.add(s1)
    db.commit()
    db.add(CompanySource(company_id=company.id, source_id=s1.id))
    db.commit()

    try:
        rows = build_export_rows(db, job_run.id)
        assert "https://osm.example/1" in rows[0].source_urls
    finally:
        _cleanup(db, job.id, [company.id])
        src = db.get(Source, s1.id)
        if src is not None:
            db.delete(src)
        db.commit()


def test_one_company_one_row_despite_many_related_records(committing_db_session):
    db = committing_db_session
    job, job_run = _make_job_run(db)
    company = _make_company(db)
    _link(db, job_run, company)

    for i in range(3):
        db.add(CompanyPhone(company_id=company.id, phone_raw=f"05000000{i}", phone_normalized=f"+38050000000{i}"))
    for i in range(2):
        db.add(CompanyEmail(company_id=company.id, email=f"e{i}@example.com"))
    db.add(Address(company_id=company.id, city="Kyiv", street="Street 1"))
    db.add(Address(company_id=company.id, city="Kyiv", street="Street 2"))
    db.commit()

    try:
        rows = build_export_rows(db, job_run.id)
        assert len(rows) == 1
    finally:
        _cleanup(db, job.id, [company.id])


def test_only_job_run_companies_included(committing_db_session):
    db = committing_db_session
    job, job_run = _make_job_run(db)
    included = _make_company(db, canonical_name="Included Co", normalized_name="included co")
    excluded = _make_company(db, canonical_name="Excluded Co", normalized_name="excluded co")
    _link(db, job_run, included)

    try:
        rows = build_export_rows(db, job_run.id)
        names = {r.company_name for r in rows}
        assert "Included Co" in names
        assert "Excluded Co" not in names
    finally:
        _cleanup(db, job.id, [included.id, excluded.id])


def test_another_job_run_companies_excluded(committing_db_session):
    db = committing_db_session
    job1, job_run1 = _make_job_run(db)
    job2, job_run2 = _make_job_run(db)

    company_a = _make_company(db, canonical_name="Company A", normalized_name="company a")
    company_b = _make_company(db, canonical_name="Company B", normalized_name="company b")
    _link(db, job_run1, company_a)
    _link(db, job_run2, company_b)

    try:
        rows1 = build_export_rows(db, job_run1.id)
        rows2 = build_export_rows(db, job_run2.id)
        assert {r.company_name for r in rows1} == {"Company A"}
        assert {r.company_name for r in rows2} == {"Company B"}
    finally:
        _cleanup(db, job1.id, [company_a.id])
        _cleanup(db, job2.id, [company_b.id])


def test_deterministic_sort_order(committing_db_session):
    db = committing_db_session
    job, job_run = _make_job_run(db)

    c1 = _make_company(db, canonical_name="Zeta", normalized_name="zeta", country="UA", region="Kyiv", city="Kyiv")
    c2 = _make_company(db, canonical_name="Alpha", normalized_name="alpha", country="UA", region="Kyiv", city="Kyiv")
    _link(db, job_run, c1)
    _link(db, job_run, c2)

    try:
        rows_1 = build_export_rows(db, job_run.id)
        rows_2 = build_export_rows(db, job_run.id)
        order_1 = [r.company_id for r in rows_1]
        order_2 = [r.company_id for r in rows_2]
        assert order_1 == order_2
        # normalized_name ascending within same country/region/city -> alpha before zeta
        names_in_order = [r.company_name for r in rows_1]
        assert names_in_order.index("Alpha") < names_in_order.index("Zeta")
    finally:
        _cleanup(db, job.id, [c1.id, c2.id])
