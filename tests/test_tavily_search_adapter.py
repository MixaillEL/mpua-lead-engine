import json
from pathlib import Path

import httpx
import pytest

from sources.tavily_search.adapter import TavilySearchAdapter
from sources.tavily_search.client import TavilySearchClient
from sources.tavily_search.query_builder import build_query_variants

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tavily_search_response.json"


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_query_variants_are_small_and_bounded():
    variants = build_query_variants("dentist", "Kyiv")
    assert 2 <= len(variants) <= 3
    assert all("Kyiv" in v for v in variants)


@pytest.mark.asyncio
async def test_adapter_returns_filtered_valid_candidates():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture)

    tavily_client = TavilySearchClient(client=_client_with_handler(handler))
    adapter = TavilySearchAdapter(client=tavily_client)

    candidates = await adapter.search(query="dentist", region="Kyiv", limit=10)

    urls = {c.website for c in candidates}
    assert "https://facebook.com/smiledentalkyiv" not in urls
    assert not any(u and u.endswith(".pdf") for u in urls)
    assert "https://smile-dental.example.com/" in urls
    assert all(c.name for c in candidates)


@pytest.mark.asyncio
async def test_adapter_respects_limit():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture)

    tavily_client = TavilySearchClient(client=_client_with_handler(handler))
    adapter = TavilySearchAdapter(client=tavily_client)

    candidates = await adapter.search(query="dentist", region="Kyiv", limit=1)
    assert len(candidates) == 1


@pytest.mark.asyncio
async def test_adapter_makes_one_request_per_query_variant():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={"results": []})

    tavily_client = TavilySearchClient(client=_client_with_handler(handler))
    adapter = TavilySearchAdapter(client=tavily_client)

    await adapter.search(query="dentist", region="Kyiv", limit=10)

    variants = build_query_variants("dentist", "Kyiv")
    assert calls["count"] == len(variants)


@pytest.mark.asyncio
async def test_adapter_tracks_requests_credits_and_cost():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    tavily_client = TavilySearchClient(client=_client_with_handler(handler))
    tavily_client.cost_per_credit_usd = 0.008
    adapter = TavilySearchAdapter(client=tavily_client)

    await adapter.search(query="dentist", region="Kyiv", limit=10)

    variants = build_query_variants("dentist", "Kyiv")
    assert adapter.last_api_requests == len(variants)
    assert adapter.last_credits_used == len(variants)
    assert adapter.last_estimated_cost_usd == round(len(variants) * 0.008, 6)


@pytest.mark.asyncio
async def test_adapter_stops_at_budget_and_reports_it():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"title": "X", "url": "https://x.example.com/"}]})

    tavily_client = TavilySearchClient(client=_client_with_handler(handler))
    tavily_client.max_requests_per_job = 1
    adapter = TavilySearchAdapter(client=tavily_client)

    candidates = await adapter.search(query="dentist", region="Kyiv", limit=100)

    assert adapter.last_budget_exceeded is True
    assert adapter.last_api_requests == 1
    assert isinstance(candidates, list)  # still returns whatever it collected, no crash


@pytest.mark.asyncio
async def test_adapter_no_fetch_details():
    adapter = TavilySearchAdapter()
    with pytest.raises(NotImplementedError):
        await adapter.fetch_details(None)
