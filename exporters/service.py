"""Main export entrypoint: JobRun -> XLSX/CSV file on disk.

Export is scoped strictly to `job_run_companies` (see dataset.py) and
only allowed for a COMPLETED JobRun — no partial export of a FAILED/
CANCELLED run in v0.1.
"""

import re
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.job import Job, JobStatus
from app.models.job_run import JobRun
from exporters.csv_exporter import rows_to_csv_bytes
from exporters.dataset import build_export_rows
from exporters.models import ExportResult
from exporters.xlsx_exporter import build_workbook

_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]+')
_WHITESPACE_RE = re.compile(r"\s+")


class JobRunNotExportableError(ValueError):
    pass


class JobRunNotFoundError(ValueError):
    pass


def _safe_slug(value: str) -> str:
    value = _INVALID_FILENAME_CHARS.sub("_", value)
    value = _WHITESPACE_RE.sub("_", value.strip())
    return value or "unnamed"


def build_filename(job: Job, job_run: JobRun, extension: str) -> str:
    date_part = (job_run.finished_at or job_run.started_at or datetime.utcnow()).strftime("%Y-%m-%d")
    preset_part = _safe_slug((job.preset or "job").lower())
    regions_part = _safe_slug("-".join(job.regions or []).lower()) or "region"
    short_id = job_run.id.replace("-", "")[:8]
    return f"{date_part}_{preset_part}_{regions_part}_{short_id}.{extension}"


def _build_summary(job: Job, job_run: JobRun, rows: list) -> dict:
    metrics = job_run.metrics or {}
    sources = metrics.get("sources", {})

    osm_attribution_required = any(
        row.source_types and "openstreetmap" in row.source_types for row in rows
    )

    def pct(key: str) -> str:
        value = metrics.get(key)
        return f"{value * 100:.1f}%" if isinstance(value, (int, float)) else None

    return {
        "job_id": job.id,
        "job_run_id": job_run.id,
        "preset": job.preset,
        "regions": ", ".join(job.regions or []),
        "status": job_run.status.value if job_run.status else None,
        "started_at": job_run.started_at,
        "finished_at": job_run.finished_at,
        "runtime_seconds": metrics.get("runtime_seconds"),
        "unique_companies": metrics.get("unique_companies"),
        "with_phone": metrics.get("with_phone"),
        "with_email": metrics.get("with_email"),
        "with_website": metrics.get("with_website"),
        "with_social": metrics.get("with_social"),
        "phone_coverage_pct": pct("phone_coverage"),
        "email_coverage_pct": pct("email_coverage"),
        "website_coverage_pct": pct("website_coverage"),
        "social_coverage_pct": pct("social_coverage"),
        "new_companies": metrics.get("new_companies"),
        "matched": metrics.get("matched"),
        "review": metrics.get("review"),
        "osm_candidates": sources.get("osm", {}).get("received"),
        "tavily_candidates": sources.get("tavily", {}).get("received"),
        "api_requests": metrics.get("api_requests"),
        "api_cost_usd": metrics.get("api_cost_usd"),
        "exported_at": datetime.utcnow(),
        "osm_attribution_required": osm_attribution_required,
    }


def export_job_run(
    db: Session,
    job_run_id: str,
    format: str,
    output_dir: Path | None = None,
) -> ExportResult:
    if format not in ("xlsx", "csv"):
        raise ValueError(f"Unsupported export format: {format!r}")

    job_run = db.get(JobRun, job_run_id)
    if job_run is None:
        raise JobRunNotFoundError(f"JobRun {job_run_id} not found")

    if job_run.status != JobStatus.completed:
        raise JobRunNotExportableError(
            f"JobRun {job_run_id} is {job_run.status.value}, not completed — partial export is not supported"
        )

    job = db.get(Job, job_run.job_id)
    if job is None:
        raise JobRunNotFoundError(f"Job {job_run.job_id} not found")

    rows = build_export_rows(db, job_run_id)
    summary = _build_summary(job, job_run, rows)

    output_dir = output_dir or Path(get_settings().EXPORT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = build_filename(job, job_run, format)
    path = output_dir / filename

    if format == "csv":
        content = rows_to_csv_bytes(rows)
        path.write_bytes(content)
    else:
        workbook = build_workbook(rows, summary)
        workbook.save(path)
        content = path.read_bytes()

    return ExportResult(
        job_run_id=job_run_id,
        format=format,
        path=path,
        rows=len(rows),
        bytes=len(content),
        created_at=datetime.utcnow(),
    )
