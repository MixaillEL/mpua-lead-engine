from db.base import Base
from app import models  # noqa: F401


def test_all_models_registered_on_metadata():
    expected_tables = {
        "jobs",
        "sources",
        "raw_records",
        "companies",
        "company_phones",
        "company_emails",
        "company_websites",
        "addresses",
        "social_links",
    }
    assert expected_tables.issubset(set(Base.metadata.tables.keys()))
