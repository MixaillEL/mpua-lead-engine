"""Job orchestration API (MLE-008).

`POST /jobs/{id}/run` executes the pipeline synchronously (blocking) —
there is no queue/worker yet. This is fine for a local/internal API;
background execution is planned as a future stage (see README).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.models.job_run import JobRun
from app.schemas.jobs import CreateJobRequest, JobResponse, JobRunResponse, RunJobResponse
from app.services.job_orchestrator import JobValidationError, run_job
from db.session import get_db

router = APIRouter(tags=["jobs"])


@router.post("/jobs", response_model=JobResponse)
def create_job(payload: CreateJobRequest, db: Session = Depends(get_db)) -> Job:
    job = Job(
        query=payload.preset,
        preset=payload.preset,
        regions=payload.regions,
        target_count=payload.target_count,
        sources_config=payload.sources,
        source_limits=payload.source_limits,
        website_enrichment=payload.website_enrichment,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.post("/jobs/{job_id}/run", response_model=RunJobResponse)
async def trigger_job_run(job_id: str, db: Session = Depends(get_db)) -> RunJobResponse:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    try:
        result = await run_job(db, job_id)
    except JobValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RunJobResponse(
        job_run_id=result.job_run_id,
        job_id=result.job_id,
        status=result.status.value,
        metrics=result.metrics,
        warnings=result.warnings,
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@router.get("/jobs/{job_id}/runs", response_model=list[JobRunResponse])
def list_job_runs(job_id: str, db: Session = Depends(get_db)) -> list[JobRun]:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return db.scalars(
        select(JobRun).where(JobRun.job_id == job_id).order_by(JobRun.created_at.desc())
    ).all()


@router.get("/job-runs/{job_run_id}", response_model=JobRunResponse)
def get_job_run(job_run_id: str, db: Session = Depends(get_db)) -> JobRun:
    job_run = db.get(JobRun, job_run_id)
    if job_run is None:
        raise HTTPException(status_code=404, detail=f"JobRun {job_run_id} not found")
    return job_run
