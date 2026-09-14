"""MLE-009 synthetic 1000-company export benchmark: builds a fake
completed JobRun with 1000 Companies (each with 2 phones, 2 emails, 1
website, 1 social), exports XLSX + CSV, and reports runtime/size/SQL
query count. Cleans up everything it creates afterward.

Usage:
    python scripts/benchmark_export_1000.py
"""

import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from sqlalchemy import event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models.company import Company  # noqa: E402
from app.models.company_email import CompanyEmail  # noqa: E402
from app.models.company_phone import CompanyPhone  # noqa: E402
from app.models.company_website import CompanyWebsite  # noqa: E402
from app.models.job import Job, JobStatus  # noqa: E402
from app.models.job_run import JobRun, PipelineStage  # noqa: E402
from app.models.job_run_company import JobRunCompany, JobRunCompanyResolution  # noqa: E402
from app.models.social_link import SocialLink, SocialPlatform, url_fingerprint  # noqa: E402
from db.session import engine  # noqa: E402
from exporters.service import export_job_run  # noqa: E402

N = 1000


def main() -> None:
    SessionLocal = sessionmaker(bind=engine, future=True)
    db = SessionLocal()

    job = Job(
        query="synthetic", preset="synthetic", regions=["Benchmark"],
        sources_config={"osm": True, "tavily": True}, source_limits={"osm": 1000, "tavily": 200},
    )
    db.add(job)
    db.commit()

    job_run = JobRun(
        job_id=job.id, status=JobStatus.completed, current_stage=PipelineStage.completed,
        metrics={
            "unique_companies": N, "with_phone": N, "with_email": N, "with_website": N, "with_social": N,
            "phone_coverage": 1.0, "email_coverage": 1.0, "website_coverage": 1.0, "social_coverage": 1.0,
            "new_companies": N, "matched": 0, "review": 0,
            "runtime_seconds": 0.0, "api_requests": 0, "api_cost_usd": 0.0,
            "sources": {"osm": {"received": N}, "tavily": {"received": 0}},
        },
    )
    db.add(job_run)
    db.commit()

    print(f"Building {N} synthetic companies...")
    company_ids = []
    for i in range(N):
        company = Company(
            canonical_name=f"Synthetic Co {i:04d}",
            normalized_name=f"synthetic co {i:04d}",
            country="UA", region="Benchmark", city="Benchmark",
        )
        db.add(company)
        db.flush()
        company_ids.append(company.id)

        db.add(CompanyPhone(company_id=company.id, phone_raw=f"+38050{i:07d}", phone_normalized=f"+38050{i:07d}", confidence=1.0))
        db.add(CompanyPhone(company_id=company.id, phone_raw=f"+38067{i:07d}", phone_normalized=f"+38067{i:07d}", confidence=0.8))
        db.add(CompanyEmail(company_id=company.id, email=f"info{i}@synthetic{i}.example.com", domain=f"synthetic{i}.example.com", confidence=1.0))
        db.add(CompanyEmail(company_id=company.id, email=f"sales{i}@synthetic{i}.example.com", domain=f"synthetic{i}.example.com", confidence=0.9))
        db.add(CompanyWebsite(company_id=company.id, url=f"https://synthetic{i}.example.com/", domain=f"synthetic{i}.example.com", is_alive=True))
        social_url = f"https://facebook.com/synthetic{i}"
        db.add(SocialLink(company_id=company.id, platform=SocialPlatform.facebook, url=social_url, url_fingerprint=url_fingerprint(social_url)))
        db.add(JobRunCompany(job_run_id=job_run.id, company_id=company.id, resolution=JobRunCompanyResolution.new, source_count=1))

        if (i + 1) % 200 == 0:
            db.commit()
            print(f"  {i + 1}/{N}")
    db.commit()

    query_count = {"count": 0}

    def _count_queries(*args, **kwargs):
        query_count["count"] += 1

    event.listen(engine, "before_cursor_execute", _count_queries)

    try:
        started = time.monotonic()
        xlsx_result = export_job_run(db, job_run.id, format="xlsx")
        xlsx_runtime = time.monotonic() - started
        xlsx_queries = query_count["count"]

        query_count["count"] = 0
        started = time.monotonic()
        csv_result = export_job_run(db, job_run.id, format="csv")
        csv_runtime = time.monotonic() - started
        csv_queries = query_count["count"]
    finally:
        event.remove(engine, "before_cursor_execute", _count_queries)

    print("\n1000-row export benchmark")
    print(f"XLSX runtime: {round(xlsx_runtime, 3)}s, rows: {xlsx_result.rows}, size: {xlsx_result.bytes} bytes, SQL queries: {xlsx_queries}")
    print(f"CSV runtime:  {round(csv_runtime, 3)}s, rows: {csv_result.rows}, size: {csv_result.bytes} bytes, SQL queries: {csv_queries}")

    xlsx_result.path.unlink(missing_ok=True)
    csv_result.path.unlink(missing_ok=True)

    for company_id in company_ids:
        c = db.get(Company, company_id)
        if c is not None:
            db.delete(c)
    db.commit()
    db.delete(db.get(Job, job.id))
    db.commit()
    db.close()


if __name__ == "__main__":
    main()
