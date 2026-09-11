import pytest
from sqlalchemy import select

from app.models.company import Company
from app.models.job import Job, JobStatus
from app.models.job_run import JobRun, PipelineStage
from app.models.job_stage_run import JobStageRun, StageStatus
from app.models.source import SourceType
from app.services import job_orchestrator as orch
from app.services.job_orchestrator import JobValidationError, run_job, validate_job_config
from enrichment.website.models import WebsiteBatchStats
from sources.schemas import RawCandidate


def _make_job(db, **overrides) -> Job:
    defaults = dict(
        query="dentist",
        preset="dentist",
        regions=["Kyiv"],
        sources_config={"osm": True, "tavily": True},
        source_limits={"osm": 10, "tavily": 10},
        website_enrichment=True,
    )
    defaults.update(overrides)
    job = Job(**defaults)
    db.add(job)
    db.commit()
    return job


def _cleanup(db, job_id, company_ids=None):
    for company_id in company_ids or []:
        company = db.get(Company, company_id)
        if company is not None:
            db.delete(company)
    db.commit()
    job = db.get(Job, job_id)
    if job is not None:
        db.delete(job)  # cascades JobRun/JobStageRun/Source/RawRecord
    db.commit()


def _candidate(name, source_type, external_id, **overrides) -> RawCandidate:
    defaults = dict(
        external_id=external_id,
        name=name,
        source_type=source_type,
        source_url=f"https://mock.local/{external_id}",
        raw_payload={"name": name},
    )
    defaults.update(overrides)
    return RawCandidate(**defaults)


class FakeOSMAdapter:
    def __init__(self, candidates=None, exc=None):
        self._candidates = candidates or []
        self._exc = exc

    async def search(self, query, region=None, limit=100):
        if self._exc:
            raise self._exc
        return self._candidates


class FakeTavilyAdapter:
    def __init__(self, candidates=None, exc=None):
        self._candidates = candidates or []
        self._exc = exc
        self.last_results_received = len(self._candidates)
        self.last_unique_domains = len(self._candidates)
        self.last_api_requests = 2
        self.last_credits_used = 2
        self.last_estimated_cost_usd = 0.016
        self.last_budget_exceeded = False

    async def search(self, query, region=None, limit=20):
        if self._exc:
            raise self._exc
        return self._candidates


async def _fake_enrich_companies_websites(db, company_ids, crawler=None):
    stats = WebsiteBatchStats(received=len(company_ids))
    stats.with_website = len(company_ids)
    stats.attempted = len(company_ids)
    stats.alive = len(company_ids)
    stats.pages_requested = len(company_ids)
    stats.pages_successful = len(company_ids)
    return [], stats


def test_validate_job_config_rejects_empty_preset():
    with pytest.raises(JobValidationError):
        validate_job_config("", ["Kyiv"], {})


def test_validate_job_config_rejects_empty_regions():
    with pytest.raises(JobValidationError):
        validate_job_config("dentist", [], {})


def test_validate_job_config_rejects_out_of_range_limits():
    with pytest.raises(JobValidationError):
        validate_job_config("dentist", ["Kyiv"], {"osm": 0})
    with pytest.raises(JobValidationError):
        validate_job_config("dentist", ["Kyiv"], {"tavily": 9999})


def test_validate_job_config_accepts_sane_config():
    validate_job_config("dentist", ["Kyiv"], {"osm": 100, "tavily": 20})


@pytest.mark.asyncio
async def test_osm_only_job(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db, sources_config={"osm": True, "tavily": False})

    candidates = [_candidate("Company A", SourceType.openstreetmap, "osm:node:1")]
    monkeypatch.setattr(orch, "OpenStreetMapAdapter", lambda: FakeOSMAdapter(candidates))
    monkeypatch.setattr(orch, "enrich_companies_websites", _fake_enrich_companies_websites)

    result = await run_job(db, job.id)

    try:
        assert result.status == JobStatus.completed
        assert result.metrics["raw_candidates"] == 1
        assert "osm" in result.metrics["sources"]
        assert "tavily" not in result.metrics["sources"]
    finally:
        company_ids = list({r for r in [result.metrics.get("new_companies")] if False})
        companies = db.scalars(select(Company)).all()
        _cleanup(db, job.id, [c.id for c in companies])


@pytest.mark.asyncio
async def test_tavily_only_job(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db, sources_config={"osm": False, "tavily": True})

    candidates = [_candidate("Company B", SourceType.web_search, "tavily:hash1", website="https://b.example.com/")]
    monkeypatch.setattr(orch, "TavilySearchAdapter", lambda: FakeTavilyAdapter(candidates))
    monkeypatch.setattr(orch.get_settings(), "TAVILY_API_KEY", "fake-key", raising=False)
    monkeypatch.setattr(orch, "enrich_companies_websites", _fake_enrich_companies_websites)

    result = await run_job(db, job.id)

    try:
        assert result.status == JobStatus.completed
        assert result.metrics["raw_candidates"] == 1
        assert "tavily" in result.metrics["sources"]
        assert "osm" not in result.metrics["sources"]
    finally:
        companies = db.scalars(select(Company)).all()
        _cleanup(db, job.id, [c.id for c in companies])


@pytest.mark.asyncio
async def test_osm_and_tavily_job(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db)

    osm_candidates = [_candidate("Company C", SourceType.openstreetmap, "osm:node:c")]
    tavily_candidates = [_candidate("Company D", SourceType.web_search, "tavily:hash-d", website="https://d.example.com/")]

    monkeypatch.setattr(orch, "OpenStreetMapAdapter", lambda: FakeOSMAdapter(osm_candidates))
    monkeypatch.setattr(orch, "TavilySearchAdapter", lambda: FakeTavilyAdapter(tavily_candidates))
    monkeypatch.setattr(orch.get_settings(), "TAVILY_API_KEY", "fake-key", raising=False)
    monkeypatch.setattr(orch, "enrich_companies_websites", _fake_enrich_companies_websites)

    result = await run_job(db, job.id)

    try:
        assert result.status == JobStatus.completed
        assert result.metrics["raw_candidates"] == 2
        assert result.metrics["new_companies"] == 2
        assert result.metrics["unique_companies"] == 2
    finally:
        companies = db.scalars(select(Company)).all()
        _cleanup(db, job.id, [c.id for c in companies])


@pytest.mark.asyncio
async def test_enrichment_enabled_calls_enrich(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db, sources_config={"osm": True, "tavily": False}, website_enrichment=True)

    candidates = [_candidate("Company E", SourceType.openstreetmap, "osm:node:e")]
    monkeypatch.setattr(orch, "OpenStreetMapAdapter", lambda: FakeOSMAdapter(candidates))

    calls = {"count": 0}

    async def tracking_enrich(db_arg, company_ids, crawler=None):
        calls["count"] += 1
        return await _fake_enrich_companies_websites(db_arg, company_ids)

    monkeypatch.setattr(orch, "enrich_companies_websites", tracking_enrich)

    result = await run_job(db, job.id)

    try:
        assert calls["count"] == 1
        stage = db.scalar(
            select(JobStageRun).where(
                JobStageRun.job_run_id == result.job_run_id,
                JobStageRun.stage == PipelineStage.website_enrichment,
            )
        )
        assert stage.status == StageStatus.completed
    finally:
        companies = db.scalars(select(Company)).all()
        _cleanup(db, job.id, [c.id for c in companies])


@pytest.mark.asyncio
async def test_enrichment_disabled_skips_stage(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db, sources_config={"osm": True, "tavily": False}, website_enrichment=False)

    candidates = [_candidate("Company F", SourceType.openstreetmap, "osm:node:f")]
    monkeypatch.setattr(orch, "OpenStreetMapAdapter", lambda: FakeOSMAdapter(candidates))

    calls = {"count": 0}

    async def tracking_enrich(db_arg, company_ids, crawler=None):
        calls["count"] += 1
        return await _fake_enrich_companies_websites(db_arg, company_ids)

    monkeypatch.setattr(orch, "enrich_companies_websites", tracking_enrich)

    result = await run_job(db, job.id)

    try:
        assert calls["count"] == 0
        stage = db.scalar(
            select(JobStageRun).where(
                JobStageRun.job_run_id == result.job_run_id,
                JobStageRun.stage == PipelineStage.website_enrichment,
            )
        )
        assert stage.status == StageStatus.skipped
        assert stage.metrics["reason"] == "disabled"
    finally:
        companies = db.scalars(select(Company)).all()
        _cleanup(db, job.id, [c.id for c in companies])


@pytest.mark.asyncio
async def test_osm_unsupported_preset_is_skipped_not_fatal(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db, preset="hvac", sources_config={"osm": True, "tavily": True})

    tavily_candidates = [_candidate("HVAC Co", SourceType.web_search, "tavily:hvac-1", website="https://hvac.example.com/")]
    monkeypatch.setattr(orch, "TavilySearchAdapter", lambda: FakeTavilyAdapter(tavily_candidates))
    monkeypatch.setattr(orch.get_settings(), "TAVILY_API_KEY", "fake-key", raising=False)
    monkeypatch.setattr(orch, "enrich_companies_websites", _fake_enrich_companies_websites)

    result = await run_job(db, job.id)

    try:
        assert result.status == JobStatus.completed
        osm_stage = db.scalar(
            select(JobStageRun).where(
                JobStageRun.job_run_id == result.job_run_id, JobStageRun.stage == PipelineStage.discovery_osm
            )
        )
        assert osm_stage.status == StageStatus.skipped
        assert osm_stage.metrics["reason"] == "preset_not_supported"
        assert any("OSM" in w for w in result.warnings)
    finally:
        companies = db.scalars(select(Company)).all()
        _cleanup(db, job.id, [c.id for c in companies])


@pytest.mark.asyncio
async def test_tavily_missing_api_key_is_skipped_not_fatal(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db, sources_config={"osm": True, "tavily": True})

    osm_candidates = [_candidate("Company G", SourceType.openstreetmap, "osm:node:g")]
    monkeypatch.setattr(orch, "OpenStreetMapAdapter", lambda: FakeOSMAdapter(osm_candidates))

    class EmptyKeySettings:
        TAVILY_API_KEY = ""

    monkeypatch.setattr(orch, "get_settings", lambda: EmptyKeySettings())
    monkeypatch.setattr(orch, "enrich_companies_websites", _fake_enrich_companies_websites)

    result = await run_job(db, job.id)

    try:
        assert result.status == JobStatus.completed
        tavily_stage = db.scalar(
            select(JobStageRun).where(
                JobStageRun.job_run_id == result.job_run_id,
                JobStageRun.stage == PipelineStage.discovery_web_search,
            )
        )
        assert tavily_stage.status == StageStatus.skipped
        assert tavily_stage.metrics["reason"] == "api_key_missing"
        assert any("Tavily" in w for w in result.warnings)
    finally:
        companies = db.scalars(select(Company)).all()
        _cleanup(db, job.id, [c.id for c in companies])


@pytest.mark.asyncio
async def test_osm_fails_tavily_succeeds_job_completes(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db)

    monkeypatch.setattr(orch, "OpenStreetMapAdapter", lambda: FakeOSMAdapter(exc=RuntimeError("Overpass down")))
    tavily_candidates = [_candidate("Company H", SourceType.web_search, "tavily:h", website="https://h.example.com/")]
    monkeypatch.setattr(orch, "TavilySearchAdapter", lambda: FakeTavilyAdapter(tavily_candidates))
    monkeypatch.setattr(orch.get_settings(), "TAVILY_API_KEY", "fake-key", raising=False)
    monkeypatch.setattr(orch, "enrich_companies_websites", _fake_enrich_companies_websites)

    result = await run_job(db, job.id)

    try:
        assert result.status == JobStatus.completed
        assert result.metrics["raw_candidates"] == 1
        assert any("OSM" in w for w in result.warnings)
    finally:
        companies = db.scalars(select(Company)).all()
        _cleanup(db, job.id, [c.id for c in companies])


@pytest.mark.asyncio
async def test_tavily_fails_osm_succeeds_job_completes(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db)

    osm_candidates = [_candidate("Company I", SourceType.openstreetmap, "osm:node:i")]
    monkeypatch.setattr(orch, "OpenStreetMapAdapter", lambda: FakeOSMAdapter(osm_candidates))
    monkeypatch.setattr(orch, "TavilySearchAdapter", lambda: FakeTavilyAdapter(exc=RuntimeError("Tavily down")))
    monkeypatch.setattr(orch.get_settings(), "TAVILY_API_KEY", "fake-key", raising=False)
    monkeypatch.setattr(orch, "enrich_companies_websites", _fake_enrich_companies_websites)

    result = await run_job(db, job.id)

    try:
        assert result.status == JobStatus.completed
        assert result.metrics["raw_candidates"] == 1
        assert any("Tavily" in w for w in result.warnings)
    finally:
        companies = db.scalars(select(Company)).all()
        _cleanup(db, job.id, [c.id for c in companies])


@pytest.mark.asyncio
async def test_both_sources_return_zero_is_not_a_fail(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db)

    monkeypatch.setattr(orch, "OpenStreetMapAdapter", lambda: FakeOSMAdapter([]))
    monkeypatch.setattr(orch, "TavilySearchAdapter", lambda: FakeTavilyAdapter([]))
    monkeypatch.setattr(orch.get_settings(), "TAVILY_API_KEY", "fake-key", raising=False)
    monkeypatch.setattr(orch, "enrich_companies_websites", _fake_enrich_companies_websites)

    result = await run_job(db, job.id)

    try:
        assert result.status == JobStatus.completed
        assert result.metrics["unique_companies"] == 0
        assert "no_candidates_found" in result.warnings
    finally:
        _cleanup(db, job.id, [])


@pytest.mark.asyncio
async def test_review_candidates_counted_and_not_persisted(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db, sources_config={"osm": True, "tavily": False})

    # Two candidates with identical name+city, nothing else -> REVIEW for the 2nd.
    c1 = _candidate(
        "Стоматологія", SourceType.openstreetmap, "osm:node:r1", city="Дніпро", region="Дніпро"
    )
    c2 = _candidate(
        "Стоматологія", SourceType.openstreetmap, "osm:node:r2", city="Дніпро", region="Дніпро"
    )
    monkeypatch.setattr(orch, "OpenStreetMapAdapter", lambda: FakeOSMAdapter([c1, c2]))
    monkeypatch.setattr(orch, "enrich_companies_websites", _fake_enrich_companies_websites)

    result = await run_job(db, job.id)

    try:
        assert result.status == JobStatus.completed
        assert result.metrics["review"] == 1
        assert result.metrics["new_companies"] == 1
        assert result.metrics["unique_companies"] == 1
    finally:
        companies = db.scalars(select(Company)).all()
        _cleanup(db, job.id, [c.id for c in companies])


@pytest.mark.asyncio
async def test_duplicate_company_from_both_sources_enriched_once(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db)

    shared_phone = "+380501112233"
    osm_candidates = [_candidate("Same Co", SourceType.openstreetmap, "osm:node:same", phone=shared_phone)]
    tavily_candidates = [_candidate("Same Co Ltd", SourceType.web_search, "tavily:same", phone=shared_phone)]

    monkeypatch.setattr(orch, "OpenStreetMapAdapter", lambda: FakeOSMAdapter(osm_candidates))
    monkeypatch.setattr(orch, "TavilySearchAdapter", lambda: FakeTavilyAdapter(tavily_candidates))
    monkeypatch.setattr(orch.get_settings(), "TAVILY_API_KEY", "fake-key", raising=False)

    seen_ids = []

    async def tracking_enrich(db_arg, company_ids, crawler=None):
        seen_ids.extend(company_ids)
        return await _fake_enrich_companies_websites(db_arg, company_ids)

    monkeypatch.setattr(orch, "enrich_companies_websites", tracking_enrich)

    result = await run_job(db, job.id)

    try:
        assert result.status == JobStatus.completed
        assert result.metrics["unique_companies"] == 1
        assert result.metrics["matched"] == 1
        assert len(seen_ids) == 1  # enriched exactly once, not twice
    finally:
        companies = db.scalars(select(Company)).all()
        _cleanup(db, job.id, [c.id for c in companies])


@pytest.mark.asyncio
async def test_job_completed_persists_job_and_run_status(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db, sources_config={"osm": True, "tavily": False})

    monkeypatch.setattr(orch, "OpenStreetMapAdapter", lambda: FakeOSMAdapter([]))
    monkeypatch.setattr(orch, "enrich_companies_websites", _fake_enrich_companies_websites)

    result = await run_job(db, job.id)

    try:
        fresh_job = db.get(Job, job.id)
        assert fresh_job.status == JobStatus.completed
        assert fresh_job.finished_at is not None

        job_run = db.get(JobRun, result.job_run_id)
        assert job_run.status == JobStatus.completed
        assert job_run.current_stage == PipelineStage.completed
        assert job_run.metrics is not None
    finally:
        _cleanup(db, job.id, [])


@pytest.mark.asyncio
async def test_fatal_error_in_identity_marks_job_failed(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db, sources_config={"osm": True, "tavily": False})

    candidates = [_candidate("Company J", SourceType.openstreetmap, "osm:node:j")]
    monkeypatch.setattr(orch, "OpenStreetMapAdapter", lambda: FakeOSMAdapter(candidates))

    def broken_resolve(*args, **kwargs):
        raise RuntimeError("identity persistence failure")

    monkeypatch.setattr(orch, "resolve_candidates", broken_resolve)

    result = await run_job(db, job.id)

    try:
        assert result.status == JobStatus.failed
        fresh_job = db.get(Job, job.id)
        assert fresh_job.status == JobStatus.failed
        assert fresh_job.error is not None
    finally:
        _cleanup(db, job.id, [])


@pytest.mark.asyncio
async def test_cancelled_between_stages_stops_pipeline(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db, sources_config={"osm": True, "tavily": True})

    async def cancel_after_osm(query, region=None, limit=100):
        job.status = JobStatus.cancelled
        db.commit()
        return []

    fake_osm = FakeOSMAdapter([])
    fake_osm.search = cancel_after_osm
    monkeypatch.setattr(orch, "OpenStreetMapAdapter", lambda: fake_osm)
    monkeypatch.setattr(orch, "enrich_companies_websites", _fake_enrich_companies_websites)

    result = await run_job(db, job.id)

    try:
        assert result.status == JobStatus.cancelled
        tavily_stage = db.scalar(
            select(JobStageRun).where(
                JobStageRun.job_run_id == result.job_run_id,
                JobStageRun.stage == PipelineStage.discovery_web_search,
            )
        )
        assert tavily_stage is None  # never started
    finally:
        _cleanup(db, job.id, [])


@pytest.mark.asyncio
async def test_metrics_persisted_on_job_run(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db, sources_config={"osm": True, "tavily": False})

    candidates = [_candidate("Company K", SourceType.openstreetmap, "osm:node:k")]
    monkeypatch.setattr(orch, "OpenStreetMapAdapter", lambda: FakeOSMAdapter(candidates))
    monkeypatch.setattr(orch, "enrich_companies_websites", _fake_enrich_companies_websites)

    result = await run_job(db, job.id)

    try:
        job_run = db.get(JobRun, result.job_run_id)
        assert job_run.metrics["raw_candidates"] == 1
        assert "sources" in job_run.metrics
        assert "osm" in job_run.metrics["sources"]
    finally:
        companies = db.scalars(select(Company)).all()
        _cleanup(db, job.id, [c.id for c in companies])


@pytest.mark.asyncio
async def test_stage_runs_persisted_for_each_stage(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db, sources_config={"osm": True, "tavily": False})

    candidates = [_candidate("Company L", SourceType.openstreetmap, "osm:node:l")]
    monkeypatch.setattr(orch, "OpenStreetMapAdapter", lambda: FakeOSMAdapter(candidates))
    monkeypatch.setattr(orch, "enrich_companies_websites", _fake_enrich_companies_websites)

    result = await run_job(db, job.id)

    try:
        stages = db.scalars(
            select(JobStageRun).where(JobStageRun.job_run_id == result.job_run_id)
        ).all()
        stage_names = {s.stage for s in stages}
        assert PipelineStage.discovery_osm in stage_names
        assert PipelineStage.normalization in stage_names
        assert PipelineStage.identity_resolution in stage_names
        assert PipelineStage.website_enrichment in stage_names
        assert PipelineStage.finalizing in stage_names
    finally:
        companies = db.scalars(select(Company)).all()
        _cleanup(db, job.id, [c.id for c in companies])


@pytest.mark.asyncio
async def test_repeat_run_creates_new_job_run_not_new_job(committing_db_session, monkeypatch):
    db = committing_db_session
    job = _make_job(db, sources_config={"osm": True, "tavily": False})

    candidates = [_candidate("Company M", SourceType.openstreetmap, "osm:node:m")]
    monkeypatch.setattr(orch, "OpenStreetMapAdapter", lambda: FakeOSMAdapter(candidates))
    monkeypatch.setattr(orch, "enrich_companies_websites", _fake_enrich_companies_websites)

    result_1 = await run_job(db, job.id)
    result_2 = await run_job(db, job.id)

    try:
        assert result_1.job_id == result_2.job_id == job.id
        assert result_1.job_run_id != result_2.job_run_id

        runs = db.scalars(select(JobRun).where(JobRun.job_id == job.id)).all()
        assert len(runs) == 2

        jobs = db.scalars(select(Job).where(Job.id == job.id)).all()
        assert len(jobs) == 1

        # idempotency: the same OSM external_id resolves to the same Company both times
        assert result_2.metrics["new_companies"] == 0
        assert result_2.metrics["matched"] == 1
    finally:
        companies = db.scalars(select(Company)).all()
        _cleanup(db, job.id, [c.id for c in companies])
