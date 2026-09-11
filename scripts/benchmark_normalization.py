"""Manual MLE-004 benchmark: OSM -> RawCandidate -> NormalizedCandidate on
real data. Hits the real public Overpass API. Does not persist anything
(no Job/Source/RawRecord/Company created). Not part of the pytest suite.

Usage:
    python scripts/benchmark_normalization.py
"""

import asyncio
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from processing.normalization.service import normalize_candidates  # noqa: E402
from sources.osm.adapter import OpenStreetMapAdapter  # noqa: E402


async def main() -> None:
    adapter = OpenStreetMapAdapter()

    started = time.monotonic()
    raw_candidates = await adapter.search(query="dentist", region="Dnipro", limit=50)
    received_runtime = round(time.monotonic() - started, 2)

    normalize_started = time.monotonic()
    normalized, stats = normalize_candidates(raw_candidates)
    normalize_runtime = round(time.monotonic() - normalize_started, 4)

    print("OSM dentist / Dnipro / limit=50")
    print(f"received:        {stats.received}")
    print(f"normalized:      {stats.normalized}")
    print(f"failed:          {stats.failed}")
    print(f"valid_phone:     {stats.phones_valid} / present {stats.phones_present}")
    print(f"invalid_phone:   {stats.phones_invalid}")
    print(f"valid_email:     {stats.emails_valid} / present {stats.emails_present}")
    print(f"invalid_email:   {stats.emails_invalid}")
    print(f"valid_domain:    {stats.domains_valid} / present {stats.websites_present}")
    print(f"invalid_domain:  {stats.domains_invalid}")
    print(f"fetch runtime:   {received_runtime}s")
    print(f"normalize runtime: {normalize_runtime}s")

    print("\n5 sample raw -> normalized records:")
    for candidate, norm in list(zip(raw_candidates, normalized))[:5]:
        print("-" * 60)
        print(f"raw.name            = {candidate.name!r}")
        print(f"normalized_name     = {norm.normalized_name!r}")
        print(f"raw.phone           = {candidate.phone!r}")
        print(f"phone_normalized    = {norm.phone_normalized!r}")
        print(f"raw.website         = {candidate.website!r}")
        print(f"website_domain      = {norm.website_domain!r}")
        print(f"raw.raw_address     = {candidate.raw_address!r}")
        print(f"normalized_address  = {norm.normalized_address!r}")


if __name__ == "__main__":
    asyncio.run(main())
