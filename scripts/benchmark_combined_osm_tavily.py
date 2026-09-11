"""MLE-007 combined benchmark: OSM baseline vs OSM + Tavily, on
dentist/Kyiv. Runs the full pipeline for both sources, merges via the
existing identity resolver, enriches new companies' websites (MLE-006),
and reports the coverage delta + Tavily cost economics. Uses the real
public Overpass API and the real Tavily Search API. Cleans up everything
it creates afterward.

Usage:
    python scripts/benchmark_combined_osm_tavily.py
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

from app.core.config import get_settings  # noqa: E402
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
from processing.identity.models import Decision  # noqa: E402
from processing.identity.service import resolve_candidates  # noqa: E402
from processing.normalization.service import normalize_candidates  # noqa: E402
from sources.osm.adapter import OpenStreetMapAdapter  # noqa: E402
from sources.tavily_search.adapter import TavilySearchAdapter  # noqa: E402


def _coverage(db, company_ids):
    if not company_ids:
        return {"with_website": 0, "with_phone": 0, "with_email": 0, "with_social": 0}

    def _count(model):
        return len(
            set(r[0] for r in db.execute(select(model.company_id).where(model.company_id.in_(company_ids))))
        )

    return {
        "with_website": _count(CompanyWebsite),
        "with_phone": _count(CompanyPhone),
        "with_email": _count(CompanyEmail),
        "with_social": _count(SocialLink),
    }


async def main() -> None:
    settings = get_settings()
    if not settings.TAVILY_API_KEY:
        print("TAVILY_API_KEY not configured - aborting combined benchmark.")
        return

    SessionLocal = sessionmaker(bind=engine, future=True)
    db = SessionLocal()

    job = Job(query="dentist")
    db.add(job)
    db.commit()

    try:
        # ---------- OSM baseline ----------
        osm_adapter = OpenStreetMapAdapter()
        osm_raw = await osm_adapter.search(query="dentist", region="Kyiv", limit=100)
        osm_normalized, _ = normalize_candidates(osm_raw)

        osm_pairs = []
        for raw, norm in zip(osm_raw, osm_normalized):
            record = persist_candidate(db, job_id=job.id, candidate=raw)
            osm_pairs.append((norm, record.source_id))
        db.commit()

        osm_results, osm_stats = resolve_candidates(db, osm_pairs)
        osm_company_ids = list({r.company_id for r in osm_results if r.company_id})

        osm_before = _coverage(db, osm_company_ids)
        print("OSM baseline")
        print(f"companies:    {len(osm_company_ids)}")
        print(f"with_website: {osm_before['with_website']}")
        print(f"with_phone:   {osm_before['with_phone']}")
        print(f"with_email:   {osm_before['with_email']}")
        print(f"with_social:  {osm_before['with_social']}")

        # ---------- Tavily ----------
        tavily_adapter = TavilySearchAdapter()
        started = time.monotonic()
        tavily_raw = await tavily_adapter.search(query="dentist", region="Kyiv", limit=20)
        tavily_runtime = time.monotonic() - started
        tavily_normalized, _ = normalize_candidates(tavily_raw)

        tavily_pairs = []
        for raw, norm in zip(tavily_raw, tavily_normalized):
            record = persist_candidate(db, job_id=job.id, candidate=raw)
            tavily_pairs.append((norm, record.source_id))
        db.commit()

        tavily_results, tavily_stats = resolve_candidates(db, tavily_pairs)

        matched_existing = sum(1 for r in tavily_results if r.decision == Decision.MATCH)
        new_from_tavily = [r.company_id for r in tavily_results if r.decision == Decision.NEW]
        review_count = sum(1 for r in tavily_results if r.decision == Decision.REVIEW)

        all_company_ids = list({*osm_company_ids, *[r.company_id for r in tavily_results if r.company_id]})

        print("\nTavily standalone")
        print(f"api_requests:      {tavily_adapter.last_api_requests}")
        print(f"credits_used:      {tavily_adapter.last_credits_used}")
        print(f"estimated_cost:    ${tavily_adapter.last_estimated_cost_usd}")
        print(f"results_received:  {tavily_adapter.last_results_received}")
        print(f"unique_domains:    {tavily_adapter.last_unique_domains}")
        print(f"valid_candidates:  {len(tavily_raw)}")
        print(f"runtime:           {round(tavily_runtime, 2)}s")

        print("\nOSM + Tavily BEFORE enrichment")
        print(f"tavily_candidates: {len(tavily_raw)}")
        print(f"matched_existing:  {matched_existing}")
        print(f"new_companies:     {len(new_from_tavily)}")
        print(f"review:            {review_count}")
        print(f"final_unique_companies: {len(all_company_ids)}")

        # ---------- Enrich the newly-created Tavily companies ----------
        results_enrich, enrich_stats = await enrich_companies_websites(db, new_from_tavily)

        after = _coverage(db, all_company_ids)
        print("\nAFTER enrichment (all companies)")
        print(f"with_website: {after['with_website']}")
        print(f"with_phone:   {after['with_phone']}")
        print(f"with_email:   {after['with_email']}")
        print(f"with_social:  {after['with_social']}")

        # ---------- Cost KPIs ----------
        cost = tavily_adapter.last_estimated_cost_usd
        new_count = max(len(new_from_tavily), 1)
        phone_companies = len(
            set(r[0] for r in db.execute(select(CompanyPhone.company_id).where(CompanyPhone.company_id.in_(new_from_tavily))))
        )
        email_companies = len(
            set(r[0] for r in db.execute(select(CompanyEmail.company_id).where(CompanyEmail.company_id.in_(new_from_tavily))))
        )
        print("\nCost KPIs")
        print(f"cost_per_new_company:    ${round(cost / new_count, 5)}")
        print(f"cost_per_phone_company:  ${round(cost / max(phone_companies, 1), 5)}")
        print(f"cost_per_email_company:  ${round(cost / max(email_companies, 1), 5)}")

        # ---------- Idempotency: re-run Tavily candidates through identity ----------
        tavily_results_2, tavily_stats_2 = resolve_candidates(db, tavily_pairs)
        new_count_2 = sum(1 for r in tavily_results_2 if r.decision == Decision.NEW)
        print("\nSecond run (idempotency check)")
        print(f"new_companies: {new_count_2} (expected 0)")

    finally:
        db.rollback()
        fresh_job = db.get(Job, job.id)
        if fresh_job is not None:
            db.delete(fresh_job)
        for company in db.scalars(select(Company)).all():
            db.delete(company)
        db.commit()
        for source in db.scalars(select(Source)).all():
            db.delete(source)
        db.commit()
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
