"""MLE-008 CLI entrypoint: create a Job (if needed) and run it end to end
through the orchestrator. This is the "one command instead of five manual
scripts" entrypoint.

Usage:
    python scripts/run_job.py --preset dentist --region Kyiv \
        --osm-limit 100 --tavily-limit 20 --enrich

    python scripts/run_job.py --preset hvac --region Kyiv --region Lviv \
        --no-osm --tavily-limit 20 --enrich
"""

import argparse
import asyncio
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models.job import Job  # noqa: E402
from app.services.job_orchestrator import JobValidationError, run_job  # noqa: E402
from db.session import engine  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MPUA Lead Engine job pipeline end to end.")
    parser.add_argument("--preset", required=True, help="dentist | car_repair | car_parts | hvac")
    parser.add_argument("--region", action="append", required=True, dest="regions", help="repeatable")
    parser.add_argument("--osm-limit", type=int, default=100)
    parser.add_argument("--tavily-limit", type=int, default=20)
    parser.add_argument("--no-osm", action="store_true")
    parser.add_argument("--no-tavily", action="store_true")
    parser.add_argument("--enrich", action="store_true", default=True)
    parser.add_argument("--no-enrich", dest="enrich", action="store_false")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    SessionLocal = sessionmaker(bind=engine, future=True)
    db = SessionLocal()

    job = Job(
        query=args.preset,
        preset=args.preset,
        regions=args.regions,
        sources_config={"osm": not args.no_osm, "tavily": not args.no_tavily},
        source_limits={"osm": args.osm_limit, "tavily": args.tavily_limit},
        website_enrichment=args.enrich,
    )
    db.add(job)
    db.commit()

    try:
        result = await run_job(db, job.id)
    except JobValidationError as exc:
        print(f"Invalid job configuration: {exc}")
        return

    m = result.metrics

    if result.status.value != "completed":
        print(f"JOB {result.status.value.upper()}")
        if result.warnings:
            print("\nWarnings:")
            for w in result.warnings:
                print(f"  - {w}")
        return

    print("JOB COMPLETED\n")
    print(f"Companies: {m.get('unique_companies', 0)}")
    print(f"Phone: {m.get('with_phone', 0)}")
    print(f"Email: {m.get('with_email', 0)}")
    print(f"Website: {m.get('with_website', 0)}")
    print(f"Social: {m.get('with_social', 0)}")
    print()
    print(f"Phone coverage: {m.get('phone_coverage', 0) * 100:.1f}%")
    print(f"Email coverage: {m.get('email_coverage', 0) * 100:.1f}%")
    print()
    print(f"Review: {m.get('review', 0)}")
    print()
    print(f"Tavily requests: {m.get('api_requests', 0)}")
    print(f"External cost: ${m.get('api_cost_usd', 0)}")
    print()
    print(f"Runtime: {m.get('runtime_seconds', 0)}s")

    if result.warnings:
        print("\nWarnings:")
        for w in result.warnings:
            print(f"  - {w}")

    print(f"\nJob ID: {job.id}")
    print(f"JobRun ID: {result.job_run_id}")


if __name__ == "__main__":
    asyncio.run(main())
