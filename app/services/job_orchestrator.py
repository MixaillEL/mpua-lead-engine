"""MLE-008 end-to-end orchestrator: the single entrypoint that runs the
whole pipeline for a Job specification.

    CREATED
    -> DISCOVERY_OSM -> DISCOVERY_WEB_SEARCH
    -> NORMALIZATION -> IDENTITY_RESOLUTION
    -> WEBSITE_ENRICHMENT
    -> FINALIZING
    -> COMPLETED / FAILED / CANCELLED

Soft failure (one discovery source unavailable) never fails the Job as
long as at least the pipeline itself completes; fatal errors (DB down,
normalization/identity crash) mark the Job FAILED. Each stage commits its
own persisted state — one website timeout never rolls back discovery.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.company_email import CompanyEmail
from app.models.company_phone import CompanyPhone
from app.models.company_website import CompanyWebsite
from app.models.job import Job, JobStatus
from app.models.job_run import JobRun, PipelineStage
from app.models.job_run_company import JobRunCompany, JobRunCompanyResolution
from app.models.job_stage_run import JobStageRun, StageStatus
from app.models.social_link import SocialLink
from app.services.source_runner import persist_candidate
from enrichment.website.service import enrich_companies_websites
from processing.identity.models import Decision
from processing.identity.service import resolve_candidates
from processing.normalization.models import NormalizedCandidate
from processing.normalization.service import normalize_candidate
from sources.osm.adapter import OpenStreetMapAdapter
from sources.osm.tag_mapping import get_preset as get_osm_preset
from sources.schemas import RawCandidate
from sources.tavily_search.adapter import TavilySearchAdapter
from sources.tavily_search.client import TavilySearchError

logger = logging.getLogger("mpua.job_orchestrator")

# Validation limits (spec #34) — no sensible-maximum config knob needed
# yet, kept as plain module constants.
OSM_LIMIT_MAX = 1000
TAVILY_LIMIT_MAX = 200


@dataclass
class JobRunResult:
    job_run_id: str
    job_id: str
    status: JobStatus
    metrics: dict
    warnings: list[str] = field(default_factory=list)


class JobValidationError(ValueError):
    pass


def validate_job_config(preset: str, regions: list[str], source_limits: dict) -> None:
    if not preset or not preset.strip():
        raise JobValidationError("preset must not be empty")
    if not regions:
        raise JobValidationError("regions must not be empty")

    osm_limit = source_limits.get("osm")
    if osm_limit is not None and not (1 <= osm_limit <= OSM_LIMIT_MAX):
        raise JobValidationError(f"osm limit must be between 1 and {OSM_LIMIT_MAX}")

    tavily_limit = source_limits.get("tavily")
    if tavily_limit is not None and not (1 <= tavily_limit <= TAVILY_LIMIT_MAX):
        raise JobValidationError(f"tavily limit must be between 1 and {TAVILY_LIMIT_MAX}")


def _start_stage(db: Session, job_run: JobRun, stage: PipelineStage) -> JobStageRun:
    stage_run = JobStageRun(
        job_run_id=job_run.id, stage=stage, status=StageStatus.running, started_at=datetime.utcnow()
    )
    db.add(stage_run)
    job_run.current_stage = stage
    db.commit()
    return stage_run


def _finish_stage(
    db: Session,
    stage_run: JobStageRun,
    status: StageStatus,
    input_count: int | None = None,
    output_count: int | None = None,
    metrics: dict | None = None,
    error: str | None = None,
) -> None:
    stage_run.status = status
    stage_run.finished_at = datetime.utcnow()
    stage_run.input_count = input_count
    stage_run.output_count = output_count
    stage_run.metrics = metrics
    stage_run.error = error
    db.commit()


def _record_job_run_companies(db: Session, job_run_id: str, identity_results: list) -> None:
    """One JobRunCompany row per Company this run touched (NEW or MATCH).
    REVIEW is excluded — it never persists a Company. Handles OSM+Tavily
    resolving to the same Company within one run by aggregating
    source_count and upgrading resolution to "new" if any contributing
    result created it.
    """

    by_company: dict[str, dict] = {}
    for result in identity_results:
        if not result.company_id or result.decision not in (Decision.NEW, Decision.MATCH):
            continue
        entry = by_company.setdefault(result.company_id, {"count": 0, "is_new": False})
        entry["count"] += 1
        if result.decision == Decision.NEW:
            entry["is_new"] = True

    for company_id, entry in by_company.items():
        existing = db.scalar(
            select(JobRunCompany).where(
                JobRunCompany.job_run_id == job_run_id, JobRunCompany.company_id == company_id
            )
        )
        resolution = JobRunCompanyResolution.new if entry["is_new"] else JobRunCompanyResolution.matched
        if existing is None:
            db.add(
                JobRunCompany(
                    job_run_id=job_run_id,
                    company_id=company_id,
                    resolution=resolution,
                    source_count=entry["count"],
                )
            )
        else:
            existing.source_count += entry["count"]
            if resolution == JobRunCompanyResolution.new:
                existing.resolution = JobRunCompanyResolution.new

    db.commit()


def _is_cancelled(db: Session, job_id: str) -> bool:
    db.expire_all()
    job = db.get(Job, job_id)
    return job is not None and job.status == JobStatus.cancelled


async def _run_osm_discovery(
    db: Session, job_run: JobRun, job: Job
) -> tuple[list[tuple[RawCandidate, str]], dict, list[str]]:
    stage_run = _start_stage(db, job_run, PipelineStage.discovery_osm)
    warnings: list[str] = []
    pairs: list[tuple[RawCandidate, str]] = []

    limit = (job.source_limits or {}).get("osm", 100)
    metrics = {"requested": 0, "received": 0, "saved": 0, "failed": 0, "http_requests": 0, "regions": {}}

    try:
        get_osm_preset(job.preset)  # raises ValueError if unsupported
    except ValueError:
        _finish_stage(
            db, stage_run, StageStatus.skipped, output_count=0,
            metrics={"reason": "preset_not_supported"},
        )
        warnings.append(f"OSM: preset '{job.preset}' is not supported, stage skipped")
        return pairs, metrics, warnings

    adapter = OpenStreetMapAdapter()

    try:
        for region in job.regions:
            candidates = await adapter.search(query=job.preset, region=region, limit=limit)
            metrics["requested"] += limit
            metrics["received"] += len(candidates)
            metrics["http_requests"] += 1
            region_saved = 0
            for candidate in candidates:
                try:
                    with db.begin_nested():
                        record = persist_candidate(db, job_id=job.id, candidate=candidate)
                    pairs.append((candidate, record.source_id))
                    region_saved += 1
                except Exception as exc:  # noqa: BLE001
                    metrics["failed"] += 1
                    logger.warning("osm discovery: failed to persist candidate", exc_info=True)
            metrics["saved"] += region_saved
            metrics["regions"][region] = {"received": len(candidates), "saved": region_saved}
            db.commit()

        _finish_stage(
            db, stage_run, StageStatus.completed,
            input_count=metrics["requested"], output_count=metrics["saved"], metrics=metrics,
        )
    except Exception as exc:  # noqa: BLE001 - soft failure: OSM unavailable must not fail the Job
        db.rollback()
        _finish_stage(db, stage_run, StageStatus.failed, metrics=metrics, error=str(exc))
        warnings.append(f"OSM discovery unavailable: {exc}")

    return pairs, metrics, warnings


async def _run_tavily_discovery(
    db: Session, job_run: JobRun, job: Job
) -> tuple[list[tuple[RawCandidate, str]], dict, list[str]]:
    stage_run = _start_stage(db, job_run, PipelineStage.discovery_web_search)
    warnings: list[str] = []
    pairs: list[tuple[RawCandidate, str]] = []

    limit = (job.source_limits or {}).get("tavily", 20)
    metrics = {
        "requested": 0, "received": 0, "saved": 0, "failed": 0,
        "api_requests": 0, "credits_used": 0, "estimated_cost_usd": 0.0, "regions": {},
    }

    if not get_settings().TAVILY_API_KEY:
        _finish_stage(
            db, stage_run, StageStatus.skipped, output_count=0,
            metrics={"reason": "api_key_missing"},
        )
        warnings.append("Tavily: API key missing, stage skipped")
        return pairs, metrics, warnings

    adapter = TavilySearchAdapter()

    try:
        for region in job.regions:
            candidates = await adapter.search(query=job.preset, region=region, limit=limit)
            metrics["requested"] += limit
            metrics["received"] += adapter.last_results_received
            metrics["api_requests"] += adapter.last_api_requests
            metrics["credits_used"] += adapter.last_credits_used
            metrics["estimated_cost_usd"] += adapter.last_estimated_cost_usd
            if adapter.last_budget_exceeded:
                warnings.append(f"Tavily: budget limit reached for region '{region}'")

            region_saved = 0
            for candidate in candidates:
                try:
                    with db.begin_nested():
                        record = persist_candidate(db, job_id=job.id, candidate=candidate)
                    pairs.append((candidate, record.source_id))
                    region_saved += 1
                except Exception:  # noqa: BLE001
                    metrics["failed"] += 1
                    logger.warning("tavily discovery: failed to persist candidate", exc_info=True)
            metrics["saved"] += region_saved
            metrics["regions"][region] = {"received": len(candidates), "saved": region_saved}
            db.commit()

        _finish_stage(
            db, stage_run, StageStatus.completed,
            input_count=metrics["requested"], output_count=metrics["saved"], metrics=metrics,
        )
    except TavilySearchError as exc:  # soft failure
        db.rollback()
        _finish_stage(db, stage_run, StageStatus.failed, metrics=metrics, error=str(exc))
        warnings.append(f"Tavily discovery unavailable: {exc}")
    except Exception as exc:  # noqa: BLE001 - still treated as soft (a discovery source failing)
        db.rollback()
        _finish_stage(db, stage_run, StageStatus.failed, metrics=metrics, error=str(exc))
        warnings.append(f"Tavily discovery failed: {exc}")

    return pairs, metrics, warnings


def _run_normalization(
    db: Session, job_run: JobRun, all_pairs: list[tuple[RawCandidate, str]]
) -> tuple[list[tuple[NormalizedCandidate, str]], dict]:
    stage_run = _start_stage(db, job_run, PipelineStage.normalization)

    normalized_pairs: list[tuple[NormalizedCandidate, str]] = []
    metrics = {
        "received": len(all_pairs), "normalized": 0, "failed": 0,
        "phones_present": 0, "phones_valid": 0,
        "emails_present": 0, "emails_valid": 0,
        "websites_present": 0, "domains_valid": 0,
    }

    for candidate, source_id in all_pairs:
        try:
            normalized = normalize_candidate(candidate)
        except Exception:  # noqa: BLE001 - one bad candidate must not fail the batch
            metrics["failed"] += 1
            logger.warning("normalization stage: failed to normalize candidate", exc_info=True)
            continue

        normalized_pairs.append((normalized, source_id))
        metrics["normalized"] += 1

        if candidate.phone:
            metrics["phones_present"] += 1
            if normalized.phone_normalized:
                metrics["phones_valid"] += 1
        if candidate.email:
            metrics["emails_present"] += 1
            if normalized.email_normalized:
                metrics["emails_valid"] += 1
        if candidate.website:
            metrics["websites_present"] += 1
            if normalized.website_domain:
                metrics["domains_valid"] += 1

    _finish_stage(
        db, stage_run, StageStatus.completed,
        input_count=len(all_pairs), output_count=metrics["normalized"], metrics=metrics,
    )
    return normalized_pairs, metrics


async def run_job(db: Session, job_id: str) -> JobRunResult:
    started = time.monotonic()
    job = db.get(Job, job_id)
    if job is None:
        raise ValueError(f"Job {job_id} not found")

    validate_job_config(job.preset or "", job.regions or [], job.source_limits or {})

    job_run = JobRun(job_id=job.id, status=JobStatus.running, current_stage=PipelineStage.created)
    job_run.started_at = datetime.utcnow()
    db.add(job_run)

    job.status = JobStatus.running
    job.started_at = datetime.utcnow()
    db.commit()

    warnings: list[str] = []
    sources_config = job.sources_config or {}
    metrics_by_source: dict = {}

    def _fail_job(error_message: str) -> JobRunResult:
        job_run.status = JobStatus.failed
        job_run.current_stage = PipelineStage.failed
        job_run.finished_at = datetime.utcnow()
        job_run.error = error_message
        job.status = JobStatus.failed
        job.finished_at = datetime.utcnow()
        job.error = error_message
        db.commit()
        return JobRunResult(
            job_run_id=job_run.id, job_id=job.id, status=JobStatus.failed,
            metrics={"sources": metrics_by_source}, warnings=warnings,
        )

    def _cancel_job() -> JobRunResult:
        job_run.status = JobStatus.cancelled
        job_run.current_stage = PipelineStage.cancelled
        job_run.finished_at = datetime.utcnow()
        job.status = JobStatus.cancelled
        job.finished_at = datetime.utcnow()
        db.commit()
        return JobRunResult(
            job_run_id=job_run.id, job_id=job.id, status=JobStatus.cancelled,
            metrics={"sources": metrics_by_source}, warnings=warnings,
        )

    # ---------------- Discovery ----------------
    all_pairs: list[tuple[RawCandidate, str]] = []

    if sources_config.get("osm", True):
        if _is_cancelled(db, job.id):
            return _cancel_job()
        osm_pairs, osm_metrics, osm_warnings = await _run_osm_discovery(db, job_run, job)
        all_pairs.extend(osm_pairs)
        metrics_by_source["osm"] = osm_metrics
        warnings.extend(osm_warnings)

    if sources_config.get("tavily", True):
        if _is_cancelled(db, job.id):
            return _cancel_job()
        tavily_pairs, tavily_metrics, tavily_warnings = await _run_tavily_discovery(db, job_run, job)
        all_pairs.extend(tavily_pairs)
        metrics_by_source["tavily"] = tavily_metrics
        warnings.extend(tavily_warnings)

    if not all_pairs:
        warnings.append("no_candidates_found")

    # ---------------- Normalization ----------------
    if _is_cancelled(db, job.id):
        return _cancel_job()

    try:
        normalized_pairs, norm_metrics = _run_normalization(db, job_run, all_pairs)
    except Exception as exc:  # noqa: BLE001 - fatal: normalization subsystem crash
        logger.exception("normalization stage crashed")
        return _fail_job(f"Normalization stage failed: {exc}")

    # ---------------- Identity resolution ----------------
    if _is_cancelled(db, job.id):
        return _cancel_job()

    stage_run = _start_stage(db, job_run, PipelineStage.identity_resolution)
    try:
        identity_results, identity_stats = resolve_candidates(db, normalized_pairs)
    except Exception as exc:  # noqa: BLE001 - fatal: identity persistence failure
        db.rollback()
        _finish_stage(db, stage_run, StageStatus.failed, error=str(exc))
        logger.exception("identity resolution stage crashed")
        return _fail_job(f"Identity resolution stage failed: {exc}")

    identity_metrics = identity_stats.as_dict()
    _finish_stage(
        db, stage_run, StageStatus.completed,
        input_count=len(normalized_pairs), output_count=identity_stats.new + identity_stats.matched,
        metrics=identity_metrics,
    )

    # Only NEW/MATCH company ids go into enrichment; a single Company that
    # matched from both OSM and Tavily is enriched exactly once (set).
    unique_company_ids = {
        r.company_id for r in identity_results if r.company_id and r.decision in (Decision.NEW, Decision.MATCH)
    }
    review_count = sum(1 for r in identity_results if r.decision == Decision.REVIEW)

    _record_job_run_companies(db, job_run.id, identity_results)

    # ---------------- Website enrichment ----------------
    enrichment_metrics = {"attempted": 0, "alive": 0, "dead": 0, "failed": 0, "pages_requested": 0}

    if job.website_enrichment and unique_company_ids:
        if _is_cancelled(db, job.id):
            return _cancel_job()

        stage_run = _start_stage(db, job_run, PipelineStage.website_enrichment)
        try:
            _, enrich_stats = await enrich_companies_websites(db, list(unique_company_ids))
            enrichment_metrics = enrich_stats.as_dict()
            _finish_stage(
                db, stage_run, StageStatus.completed,
                input_count=len(unique_company_ids), output_count=enrich_stats.attempted,
                metrics=enrichment_metrics,
            )
        except Exception as exc:  # noqa: BLE001 - fatal: enrichment subsystem crash
            db.rollback()
            _finish_stage(db, stage_run, StageStatus.failed, error=str(exc))
            logger.exception("website enrichment stage crashed")
            return _fail_job(f"Website enrichment stage failed: {exc}")
    else:
        stage_run = _start_stage(db, job_run, PipelineStage.website_enrichment)
        reason = "disabled" if not job.website_enrichment else "no_companies"
        _finish_stage(db, stage_run, StageStatus.skipped, metrics={"reason": reason})

    metrics_by_source["website_enrichment"] = enrichment_metrics

    # ---------------- Finalizing ----------------
    stage_run = _start_stage(db, job_run, PipelineStage.finalizing)

    def _coverage_count(model):
        if not unique_company_ids:
            return 0
        return len(
            set(r[0] for r in db.execute(select(model.company_id).where(model.company_id.in_(unique_company_ids))))
        )

    with_phone = _coverage_count(CompanyPhone)
    with_email = _coverage_count(CompanyEmail)
    with_website = _coverage_count(CompanyWebsite)
    with_social = _coverage_count(SocialLink)

    unique_companies = len(unique_company_ids)
    runtime_seconds = round(time.monotonic() - started, 3)

    api_requests = metrics_by_source.get("tavily", {}).get("api_requests", 0)
    api_cost_usd = round(metrics_by_source.get("tavily", {}).get("estimated_cost_usd", 0.0), 6)
    http_requests = (
        metrics_by_source.get("osm", {}).get("http_requests", 0)
        + api_requests
        + enrichment_metrics.get("pages_requested", 0)
    )

    final_metrics = {
        "raw_candidates": len(all_pairs),
        "unique_companies": unique_companies,
        "new_companies": identity_stats.new,
        "matched": identity_stats.matched,
        "review": review_count,
        "with_phone": with_phone,
        "with_email": with_email,
        "with_website": with_website,
        "with_social": with_social,
        "duplicates_removed_or_matched": identity_stats.matched,
        "api_requests": api_requests,
        "api_cost_usd": api_cost_usd,
        "total_external_cost_usd": api_cost_usd,
        "http_requests": http_requests,
        "runtime_seconds": runtime_seconds,
        "phone_coverage": round(with_phone / unique_companies, 4) if unique_companies else 0.0,
        "email_coverage": round(with_email / unique_companies, 4) if unique_companies else 0.0,
        "website_coverage": round(with_website / unique_companies, 4) if unique_companies else 0.0,
        "social_coverage": round(with_social / unique_companies, 4) if unique_companies else 0.0,
        "normalization": norm_metrics,
        "identity": identity_metrics,
        "sources": metrics_by_source,
    }

    _finish_stage(
        db, stage_run, StageStatus.completed, output_count=unique_companies, metrics=final_metrics
    )

    job_run.status = JobStatus.completed
    job_run.current_stage = PipelineStage.completed
    job_run.finished_at = datetime.utcnow()
    job_run.metrics = final_metrics
    job.status = JobStatus.completed
    job.finished_at = datetime.utcnow()
    db.commit()

    return JobRunResult(
        job_run_id=job_run.id, job_id=job.id, status=JobStatus.completed,
        metrics=final_metrics, warnings=warnings,
    )
