"""Integration tests hitting the real Tavily Search API. Excluded from the
default `pytest` run (see addopts in pyproject.toml). Skipped (not failed)
if TAVILY_API_KEY isn't configured.

Run explicitly with:

    pytest -m tavily_integration tests/test_tavily_search_integration.py -v -s
"""

import pytest

from app.core.config import get_settings
from app.models.source import SourceType
from sources.tavily_search.adapter import TavilySearchAdapter

pytestmark = pytest.mark.tavily_integration


def _require_api_key():
    if not get_settings().TAVILY_API_KEY:
        pytest.skip("TAVILY_API_KEY not configured")


@pytest.mark.asyncio
async def test_real_tavily_search_dentist_kyiv_benchmark():
    _require_api_key()

    adapter = TavilySearchAdapter()
    candidates = await adapter.search(query="dentist", region="Kyiv", limit=20)

    assert len(candidates) >= 1
    for candidate in candidates:
        assert candidate.name
        assert candidate.source_type == SourceType.web_search
        assert candidate.website

    print(
        f"\napi_requests={adapter.last_api_requests} "
        f"credits_used={adapter.last_credits_used} "
        f"estimated_cost=${adapter.last_estimated_cost_usd} "
        f"results_received={adapter.last_results_received} "
        f"unique_domains={adapter.last_unique_domains} "
        f"valid_candidates={len(candidates)}"
    )
