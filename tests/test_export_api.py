import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.company import Company
from app.models.job import Job, JobStatus
from app.models.job_run import JobRun, PipelineStage
from app.models.job_run_company import JobRunCompany
from db.session import get_db


@pytest.fixture()
def client(committing_db_session):
    def _override_get_db():
        yield committing_db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _cleanup(db, job_id, company_id=None):
    if company_id:
        c = db.get(Company, company_id)
        if c is not None:
            db.delete(c)
        db.commit()
    job = db.get(Job, job_id)
    if job is not None:
        db.delete(job)
    db.commit()


def _make_completed_job_run(db):
    job = Job(query="dentist", preset="dentist", regions=["Kyiv"], sources_config={"osm": True}, source_limits={"osm": 10})
    db.add(job)
    db.commit()

    job_run = JobRun(job_id=job.id, status=JobStatus.completed, current_stage=PipelineStage.completed, metrics={"unique_companies": 1})
    db.add(job_run)
    db.commit()

    company = Company(canonical_name="API Test Co", normalized_name="api test co")
    db.add(company)
    db.commit()

    db.add(JobRunCompany(job_run_id=job_run.id, company_id=company.id, resolution="new", source_count=1))
    db.commit()

    return job, job_run, company


def test_xlsx_download_returns_200(committing_db_session, client, tmp_path, monkeypatch):
    db = committing_db_session
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path))
    from app.core.config import get_settings
    get_settings.cache_clear()

    job, job_run, company = _make_completed_job_run(db)
    try:
        response = client.get(f"/job-runs/{job_run.id}/export.xlsx")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert "attachment" in response.headers.get("content-disposition", "") or response.headers.get("content-disposition")
    finally:
        _cleanup(db, job.id, company.id)
        get_settings.cache_clear()


def test_csv_download_returns_200(committing_db_session, client, tmp_path, monkeypatch):
    db = committing_db_session
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path))
    from app.core.config import get_settings
    get_settings.cache_clear()

    job, job_run, company = _make_completed_job_run(db)
    try:
        response = client.get(f"/job-runs/{job_run.id}/export.csv")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
    finally:
        _cleanup(db, job.id, company.id)
        get_settings.cache_clear()


def test_filename_header_present(committing_db_session, client, tmp_path, monkeypatch):
    db = committing_db_session
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path))
    from app.core.config import get_settings
    get_settings.cache_clear()

    job, job_run, company = _make_completed_job_run(db)
    try:
        response = client.get(f"/job-runs/{job_run.id}/export.xlsx")
        assert ".xlsx" in response.headers.get("content-disposition", "")
    finally:
        _cleanup(db, job.id, company.id)
        get_settings.cache_clear()


def test_unknown_job_run_returns_404(client):
    response = client.get("/job-runs/does-not-exist/export.xlsx")
    assert response.status_code == 404


def test_non_completed_job_run_returns_409(committing_db_session, client):
    db = committing_db_session
    job = Job(query="dentist", preset="dentist", regions=["Kyiv"], sources_config={"osm": True}, source_limits={"osm": 10})
    db.add(job)
    db.commit()
    job_run = JobRun(job_id=job.id, status=JobStatus.failed, current_stage=PipelineStage.failed)
    db.add(job_run)
    db.commit()

    try:
        response = client.get(f"/job-runs/{job_run.id}/export.xlsx")
        assert response.status_code == 409
    finally:
        _cleanup(db, job.id)
