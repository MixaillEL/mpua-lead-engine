import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.job import Job
from db.session import get_db


def _cleanup(db, job_id):
    job = db.get(Job, job_id)
    if job is not None:
        db.delete(job)
    db.commit()


@pytest.fixture()
def client(committing_db_session):
    def _override_get_db():
        yield committing_db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_create_job_returns_job_response(committing_db_session, client):
    db = committing_db_session

    payload = {
        "preset": "dentist",
        "regions": ["Kyiv"],
        "sources": {"osm": True, "tavily": False},
        "source_limits": {"osm": 10, "tavily": 10},
        "website_enrichment": True,
    }
    response = client.post("/jobs", json=payload)

    try:
        assert response.status_code == 200
        body = response.json()
        assert body["preset"] == "dentist"
        assert body["regions"] == ["Kyiv"]
        assert body["status"] == "created"
    finally:
        job_id = response.json()["id"]
        _cleanup(db, job_id)


def test_get_job_not_found_returns_404():
    client = TestClient(app)
    response = client.get("/jobs/does-not-exist")
    assert response.status_code == 404


def test_get_job_run_not_found_returns_404():
    client = TestClient(app)
    response = client.get("/job-runs/does-not-exist")
    assert response.status_code == 404


def test_list_job_runs_empty_for_new_job(committing_db_session, client):
    db = committing_db_session
    job = Job(query="dentist", preset="dentist", regions=["Kyiv"], sources_config={"osm": True}, source_limits={"osm": 10})
    db.add(job)
    db.commit()

    try:
        response = client.get(f"/jobs/{job.id}/runs")
        assert response.status_code == 200
        assert response.json() == []
    finally:
        _cleanup(db, job.id)
