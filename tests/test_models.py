from app.models import (
    Company,
    CompanyEmail,
    CompanyPhone,
    CompanyWebsite,
    Job,
    JobStatus,
    Source,
    SourceType,
)


def test_create_job(db_session):
    job = Job(query="restaurants in Kyiv", target_count=50)
    db_session.add(job)
    db_session.flush()

    assert job.id is not None
    assert job.status == JobStatus.created


def test_create_company(db_session):
    company = Company(
        canonical_name="ACME Ltd",
        normalized_name="acme ltd",
        city="Kyiv",
        country="UA",
    )
    db_session.add(company)
    db_session.flush()

    assert company.id is not None
    assert company.canonical_name == "ACME Ltd"


def test_company_with_two_phones(db_session):
    company = Company(canonical_name="Phone Co", normalized_name="phone co")
    db_session.add(company)
    db_session.flush()

    phone1 = CompanyPhone(company_id=company.id, phone_raw="+380441112233")
    phone2 = CompanyPhone(company_id=company.id, phone_raw="+380445556677")
    db_session.add_all([phone1, phone2])
    db_session.flush()

    db_session.refresh(company)
    assert len(company.phones) == 2


def test_company_with_two_emails(db_session):
    company = Company(canonical_name="Email Co", normalized_name="email co")
    db_session.add(company)
    db_session.flush()

    email1 = CompanyEmail(company_id=company.id, email="info@example.com", domain="example.com")
    email2 = CompanyEmail(company_id=company.id, email="sales@example.com", domain="example.com")
    db_session.add_all([email1, email2])
    db_session.flush()

    db_session.refresh(company)
    assert len(company.emails) == 2


def test_company_with_website(db_session):
    company = Company(canonical_name="Web Co", normalized_name="web co")
    db_session.add(company)
    db_session.flush()

    website = CompanyWebsite(company_id=company.id, url="https://example.com", domain="example.com")
    db_session.add(website)
    db_session.flush()

    db_session.refresh(company)
    assert len(company.websites) == 1
    assert company.websites[0].domain == "example.com"


def test_source_linked_to_job_and_contact(db_session):
    job = Job(query="cafes in Lviv")
    db_session.add(job)
    db_session.flush()

    source = Source(source_type=SourceType.google_maps, source_url="https://maps.example", job_id=job.id)
    db_session.add(source)
    db_session.flush()

    company = Company(canonical_name="Cafe Co", normalized_name="cafe co")
    db_session.add(company)
    db_session.flush()

    phone = CompanyPhone(company_id=company.id, phone_raw="+380501234567", source_id=source.id)
    db_session.add(phone)
    db_session.flush()

    db_session.refresh(job)
    db_session.refresh(source)
    assert source in job.sources
    assert phone.source_id == source.id
    assert phone.source.source_type == SourceType.google_maps


def test_relationships_navigate_both_ways(db_session):
    company = Company(canonical_name="Rel Co", normalized_name="rel co")
    db_session.add(company)
    db_session.flush()

    phone = CompanyPhone(company_id=company.id, phone_raw="+380671112233")
    db_session.add(phone)
    db_session.flush()

    db_session.refresh(company)
    assert phone in company.phones
    assert phone.company_id == company.id
