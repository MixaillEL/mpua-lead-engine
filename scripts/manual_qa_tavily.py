"""Prints Tavily candidates (title/website) for manual relevance QA
sampling (MLE-007 #37-38). Not part of pytest.
"""

import asyncio
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from sources.tavily_search.adapter import TavilySearchAdapter  # noqa: E402


async def main() -> None:
    adapter = TavilySearchAdapter()
    candidates = await adapter.search(query="dentist", region="Kyiv", limit=20)

    print(f"api_requests={adapter.last_api_requests} credits_used={adapter.last_credits_used} "
          f"estimated_cost=${adapter.last_estimated_cost_usd} results_received={adapter.last_results_received} "
          f"unique_domains={adapter.last_unique_domains}\n")

    for i, c in enumerate(candidates, 1):
        print(f"{i:2}. {c.name}")
        print(f"    {c.website}")


if __name__ == "__main__":
    asyncio.run(main())
