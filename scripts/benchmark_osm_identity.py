"""MLE-005 OSM idempotency benchmark: OSM -> normalize -> identity resolve,
run twice against the same real OSM dataset (dentist/Dnipro/limit=50).

Expects the second run to create 0 new companies for the same source
records (idempotency). Uses the real DB configured by TEST_DB_* in .env
and cleans up everything it creates afterward.

Usage:
    python scripts/benchmark_osm_identity.py
"""

import asyncio
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.job import Job  # noqa: E402
from app.models.source import Source  # noqa: E402
from app.services.source_runner import persist_candidate  # noqa: E402
from processing.identity.service import resolve_candidates  # noqa: E402
from processing.normalization.service import normalize_candidates  # noqa: E402
from sources.osm.adapter import OpenStreetMapAdapter  # noqa: E402
from db.session import engine  # noqa: E402


async def run_once(db, job_id, label):
    adapter = OpenStreetMapAdapter()
    raw_candidates = await adapter.search(query="dentist", region="Dnipro", limit=50)
    normalized, norm_stats = normalize_candidates(raw_candidates)

    pairs = []
    for raw, norm in zip(raw_candidates, normalized):
        record = persist_candidate(db, job_id=job_id, candidate=raw)
        pairs.append((norm, record.source_id))
    db.commit()

    results, id_stats = resolve_candidates(db, pairs)

    print(f"\n{label}")
    print(f"received:    {norm_stats.received}")
    print(f"normalized:  {norm_stats.normalized}")
    print(f"new:         {id_stats.new}")
    print(f"matched:     {id_stats.matched}")
    print(f"review:      {id_stats.review}")
    print(f"companies_created: {id_stats.companies_created}")

    return id_stats


async def main() -> None:
    settings = get_settings()
    SessionLocal = sessionmaker(bind=engine, future=True)
    db = SessionLocal()

    job = Job(query="dentist")
    db.add(job)
    db.commit()

    try:
        stats_1 = await run_once(db, job.id, "First run")
        stats_2 = await run_once(db, job.id, "Second run (same dataset)")

        print("\nIdempotency check:")
        print(f"second_run companies_created = {stats_2.companies_created} (expected 0)")

        companies = db.scalars(select(Company)).all()
        print(f"\nDB counts after benchmark: companies={len(companies)}")
    finally:
        db.rollback()
        fresh_job = db.get(Job, job.id)
        if fresh_job is not None:
            db.delete(fresh_job)  # cascades Source/RawRecord
        for company in db.scalars(select(Company)).all():
            db.delete(company)
        db.commit()
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
