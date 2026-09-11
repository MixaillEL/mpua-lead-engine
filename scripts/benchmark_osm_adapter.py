"""Manual MLE-003 benchmark runner: hits the real public Overpass API.

Public Overpass endpoint = development / validation source. Runs the 3
benchmark scenarios sequentially (adapter concurrency is capped at 1
in-flight request) and prints coverage metrics. Not part of the pytest
suite.

Usage:
    python scripts/benchmark_osm_adapter.py
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sources.osm.adapter import OpenStreetMapAdapter, OverpassRequestError  # noqa: E402

SCENARIOS = [
    ("Test A", "dentist", "Dnipro", 100),
    ("Test B", "car_repair", "Kyiv", 100),
    ("Test C", "car_parts", "Lviv", 100),
]


async def run_scenario(label: str, preset: str, city: str, limit: int) -> dict:
    adapter = OpenStreetMapAdapter()
    started = time.monotonic()
    result = {
        "label": label,
        "preset": preset,
        "city": city,
        "limit": limit,
        "returned": 0,
        "with_name": 0,
        "with_phone": 0,
        "with_website": 0,
        "with_email": 0,
        "runtime": 0.0,
        "error": None,
    }

    try:
        candidates = await adapter.search(query=preset, region=city, limit=limit)
        result["returned"] = len(candidates)
        result["with_name"] = sum(1 for c in candidates if c.name)
        result["with_phone"] = sum(1 for c in candidates if c.phone)
        result["with_website"] = sum(1 for c in candidates if c.website)
        result["with_email"] = sum(1 for c in candidates if c.email)
    except OverpassRequestError as exc:
        result["error"] = str(exc)

    result["runtime"] = round(time.monotonic() - started, 2)
    return result


async def main() -> None:
    print(f"{'scenario':10} {'preset':12} {'city':8} {'returned':9} {'w/name':7} {'w/phone':8} {'w/site':7} {'w/email':8} {'runtime':8} error")
    for label, preset, city, limit in SCENARIOS:
        result = await run_scenario(label, preset, city, limit)
        print(
            f"{result['label']:10} {result['preset']:12} {result['city']:8} "
            f"{result['returned']:9} {result['with_name']:7} {result['with_phone']:8} "
            f"{result['with_website']:7} {result['with_email']:8} {result['runtime']:8} "
            f"{result['error'] or ''}"
        )


if __name__ == "__main__":
    asyncio.run(main())
