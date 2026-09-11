"""Integration tests that hit the real public Overpass API.

Excluded from the default `pytest` run (see addopts in pyproject.toml).
Run explicitly with:

    pytest -m integration tests/test_osm_integration.py -v

Public Overpass endpoint = development / validation source. Keep these
tests few and infrequent; do not add high-volume/parallel integration
tests against it.
"""

import pytest
from sqlalchemy import select

from app.models.company import Company
from app.models.job import Job
from app.models.raw_record import RawRecord
from app.models.source import Source, SourceType
from app.services.source_runner import run_source_search
from sources.osm.adapter import OpenStreetMapAdapter


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_overpass_dentist_dnipro_benchmark():
    adapter = OpenStreetMapAdapter()

    candidates = await adapter.search(query="dentist", region="Dnipro", limit=20)

    assert len(candidates) >= 1
    for candidate in candidates:
        assert candidate.name
        assert candidate.source_type == SourceType.openstreetmap
        assert candidate.source_url.startswith("https://www.openstreetmap.org/")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_osm_to_mysql(committing_db_session):
    db = committing_db_session
    job = Job(query="dentist")
    db.add(job)
    db.commit()

    try:
        adapter = OpenStreetMapAdapter()
        stats = await run_source_search(
            db=db,
            job_id=job.id,
            adapter=adapter,
            query="dentist",
            region="Dnipro",
            limit=20,
        )

        assert stats["received"] >= 1
        assert stats["saved"] == stats["received"] - stats["failed"]

        raw_records = db.scalars(select(RawRecord).where(RawRecord.job_id == job.id)).all()
        assert len(raw_records) == stats["saved"]
        assert all(r.job_id == job.id for r in raw_records)
        assert all(r.raw_payload is not None for r in raw_records)

        sources = db.scalars(select(Source).where(Source.job_id == job.id)).all()
        assert all(s.source_type == SourceType.openstreetmap for s in sources)

        companies = db.scalars(select(Company)).all()
        assert len(companies) == 0
    finally:
        fresh_job = db.get(Job, job.id)
        if fresh_job is not None:
            db.delete(fresh_job)
            db.commit()
