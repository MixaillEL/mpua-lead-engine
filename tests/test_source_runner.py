import pytest
from sqlalchemy import select

from app.models.company import Company
from app.models.job import Job
from app.models.raw_record import RawRecord
from app.models.source import Source, SourceType
from app.services.source_runner import persist_candidate, run_source_search
from sources.mock.adapter import MockAdapter
from sources.schemas import RawCandidate


def _cleanup(session, job_id: str) -> None:
    job = session.get(Job, job_id)
    if job is not None:
        session.delete(job)  # DB-level ON DELETE CASCADE removes Source/RawRecord
        session.commit()


@pytest.mark.asyncio
async def test_run_source_search_saves_100_raw_records(committing_db_session):
    db = committing_db_session
    job = Job(query="HVAC")
    db.add(job)
    db.commit()

    try:
        adapter = MockAdapter()
        stats = await run_source_search(
            db=db,
            job_id=job.id,
            adapter=adapter,
            query="HVAC",
            region="Kyiv",
            limit=100,
        )

        assert stats == {"requested": 100, "received": 100, "saved": 100, "failed": 0}

        raw_records = db.scalars(select(RawRecord).where(RawRecord.job_id == job.id)).all()
        assert len(raw_records) == 100

        sources = db.scalars(select(Source).where(Source.job_id == job.id)).all()
        assert len(sources) == 100
        assert all(s.source_type == SourceType.manual for s in sources)

        companies = db.scalars(select(Company)).all()
        # MLE-002 stops at the RAW layer: no Company rows are ever created here.
        assert len(companies) == 0
    finally:
        _cleanup(db, job.id)


@pytest.mark.asyncio
async def test_run_source_search_raw_record_linked_to_job(committing_db_session):
    db = committing_db_session
    job = Job(query="HVAC")
    db.add(job)
    db.commit()

    try:
        adapter = MockAdapter()
        await run_source_search(db=db, job_id=job.id, adapter=adapter, query="HVAC", limit=5)

        raw_records = db.scalars(select(RawRecord).where(RawRecord.job_id == job.id)).all()
        assert len(raw_records) == 5
        assert all(r.job_id == job.id for r in raw_records)
    finally:
        _cleanup(db, job.id)


@pytest.mark.asyncio
async def test_raw_payload_is_preserved_without_loss(committing_db_session):
    db = committing_db_session
    job = Job(query="HVAC")
    db.add(job)
    db.commit()

    try:
        adapter = MockAdapter()
        await run_source_search(db=db, job_id=job.id, adapter=adapter, query="HVAC", region="Kyiv", limit=1)

        raw_record = db.scalars(select(RawRecord).where(RawRecord.job_id == job.id)).first()
        assert raw_record.raw_payload["query"] == "HVAC"
        assert raw_record.raw_payload["region"] == "Kyiv"
        assert raw_record.raw_payload["external_id"] == "mock-001"
        assert raw_record.raw_payload["name"] == "Company 001"
    finally:
        _cleanup(db, job.id)


@pytest.mark.asyncio
async def test_missing_job_raises(committing_db_session):
    db = committing_db_session
    adapter = MockAdapter()

    with pytest.raises(ValueError):
        await run_source_search(db=db, job_id="does-not-exist", adapter=adapter, query="HVAC", limit=1)


def test_one_invalid_candidate_does_not_fail_the_batch(committing_db_session, monkeypatch):
    db = committing_db_session
    job = Job(query="HVAC")
    db.add(job)
    db.commit()

    valid_candidates = [
        RawCandidate(name=f"Company {i:03d}", source_type=SourceType.manual, raw_payload={"i": i})
        for i in range(1, 4)
    ]

    calls = {"count": 0}
    original_persist = persist_candidate

    def flaky_persist(session, job_id, candidate):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("simulated bad candidate")
        return original_persist(session, job_id, candidate)

    import app.services.source_runner as source_runner_module

    monkeypatch.setattr(source_runner_module, "persist_candidate", flaky_persist)

    try:
        stats_saved = 0
        stats_failed = 0
        for candidate in valid_candidates:
            try:
                with db.begin_nested():
                    flaky_persist(db, job.id, candidate)
                stats_saved += 1
            except Exception:
                stats_failed += 1
        db.commit()

        assert stats_saved == 2
        assert stats_failed == 1

        raw_records = db.scalars(select(RawRecord).where(RawRecord.job_id == job.id)).all()
        assert len(raw_records) == 2
    finally:
        _cleanup(db, job.id)


def test_repeated_run_leaves_no_leftovers(committing_db_session):
    db = committing_db_session

    job = Job(query="HVAC")
    db.add(job)
    db.commit()
    job_id = job.id
    persist_candidate(
        db,
        job_id=job_id,
        candidate=RawCandidate(name="Company 001", source_type=SourceType.manual, raw_payload={}),
    )
    db.commit()
    _cleanup(db, job_id)

    assert db.get(Job, job_id) is None
    assert db.scalars(select(RawRecord).where(RawRecord.job_id == job_id)).all() == []
    assert db.scalars(select(Source).where(Source.job_id == job_id)).all() == []
