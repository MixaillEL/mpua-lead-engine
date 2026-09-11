"""MLE-006 real-data benchmark: OSM -> normalize -> identity -> Companies
-> website enrichment. Uses the real public Overpass API and the real
website(s) found in OSM data (if any expose a website tag), so results
vary run to run. Cleans up everything it creates afterward.

Usage:
    python scripts/benchmark_website_enrichment.py
"""

import asyncio
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models.company import Company  # noqa: E402
from app.models.company_email import CompanyEmail  # noqa: E402
from app.models.company_phone import CompanyPhone  # noqa: E402
from app.models.company_website import CompanyWebsite  # noqa: E402
from app.models.job import Job  # noqa: E402
from app.models.social_link import SocialLink  # noqa: E402
from app.models.source import Source  # noqa: E402
from app.services.source_runner import persist_candidate  # noqa: E402
from db.session import engine  # noqa: E402
from enrichment.website.service import enrich_companies_websites  # noqa: E402
from processing.identity.service import resolve_candidates  # noqa: E402
from processing.normalization.service import normalize_candidates  # noqa: E402
from sources.osm.adapter import OpenStreetMapAdapter  # noqa: E402


def _coverage(db, company_ids):
    if not company_ids:
        return {"with_phone": 0, "with_email": 0, "with_social": 0}

    with_phone = len(
        set(
            r[0]
            for r in db.execute(
                select(CompanyPhone.company_id).where(CompanyPhone.company_id.in_(company_ids))
            )
        )
    )
    with_email = len(
        set(
            r[0]
            for r in db.execute(
                select(CompanyEmail.company_id).where(CompanyEmail.company_id.in_(company_ids))
            )
        )
    )
    with_social = len(
        set(
            r[0]
            for r in db.execute(
                select(SocialLink.company_id).where(SocialLink.company_id.in_(company_ids))
            )
        )
    )
    return {"with_phone": with_phone, "with_email": with_email, "with_social": with_social}


async def main() -> None:
    SessionLocal = sessionmaker(bind=engine, future=True)
    db = SessionLocal()

    job = Job(query="dentist")
    db.add(job)
    db.commit()

    try:
        adapter = OpenStreetMapAdapter()
        raw_candidates = await adapter.search(query="dentist", region="Kyiv", limit=100)
        normalized, _ = normalize_candidates(raw_candidates)

        pairs = []
        for raw, norm in zip(raw_candidates, normalized):
            record = persist_candidate(db, job_id=job.id, candidate=raw)
            pairs.append((norm, record.source_id))
        db.commit()

        id_results, id_stats = resolve_candidates(db, pairs)
        company_ids = list({r.company_id for r in id_results if r.company_id})

        with_website_ids = [
            r[0]
            for r in db.execute(
                select(CompanyWebsite.company_id).where(CompanyWebsite.company_id.in_(company_ids))
            )
        ]
        with_website_ids = list(dict.fromkeys(with_website_ids))

        before = _coverage(db, company_ids)

        print("BEFORE")
        print(f"companies:    {len(company_ids)}")
        print(f"with_website: {len(with_website_ids)}")
        print(f"with_phone:   {before['with_phone']}")
        print(f"with_email:   {before['with_email']}")
        print(f"with_social:  {before['with_social']}")

        started = time.monotonic()
        results, stats = await enrich_companies_websites(db, with_website_ids)
        runtime = time.monotonic() - started

        after = _coverage(db, company_ids)

        print("\nAFTER")
        print(f"with_phone:   {after['with_phone']}")
        print(f"with_email:   {after['with_email']}")
        print(f"with_social:  {after['with_social']}")

        print("\nAdded")
        print(f"phones_added:  {stats.phones_added}")
        print(f"emails_added:  {stats.emails_added}")
        print(f"socials_added: {stats.socials_added}")

        print("\nCrawl")
        print(f"sites_attempted:  {stats.attempted}")
        print(f"alive:            {stats.alive}")
        print(f"dead:             {stats.dead}")
        print(f"failed:           {stats.failed}")
        print(f"pages_requested:  {stats.pages_requested}")
        print(f"runtime:          {round(runtime, 2)}s")

        # Idempotency: run again on the same companies.
        results_2, stats_2 = await enrich_companies_websites(db, with_website_ids)
        print("\nSecond run (idempotency check)")
        print(f"phones_added:  {stats_2.phones_added} (expected 0)")
        print(f"emails_added:  {stats_2.emails_added} (expected 0)")
        print(f"socials_added: {stats_2.socials_added} (expected 0)")

    finally:
        db.rollback()
        fresh_job = db.get(Job, job.id)
        if fresh_job is not None:
            db.delete(fresh_job)  # cascades Source/RawRecord created by source_runner
        for company in db.scalars(select(Company)).all():
            db.delete(company)
        db.commit()
        # website-enrichment Sources aren't tied to the Job, clean separately
        for source in db.scalars(select(Source)).all():
            db.delete(source)
        db.commit()
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
