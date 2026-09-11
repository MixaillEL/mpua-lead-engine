import httpx
import pytest

import sources.tavily_search.client as client_module
from sources.tavily_search.client import TavilySearchBudgetExceeded, TavilySearchClient, TavilySearchError


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_successful_search_returns_json_and_increments_counters():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    client = TavilySearchClient(client=_client_with_handler(handler))
    data = await client.search("dentist Kyiv")

    assert data == {"results": []}
    assert client.request_count == 1
    assert client.credits_used == 1


@pytest.mark.asyncio
async def test_401_bad_key_raises_immediately_no_retry():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(401)

    client = TavilySearchClient(client=_client_with_handler(handler))
    with pytest.raises(TavilySearchError):
        await client.search("x")

    assert calls["count"] == 1
    assert client.request_count == 0


@pytest.mark.asyncio
async def test_429_gets_one_retry_then_succeeds(monkeypatch):
    monkeypatch.setattr(client_module, "RETRY_BACKOFF_SECONDS", 0.0)
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"results": []})

    client = TavilySearchClient(client=_client_with_handler(handler))
    data = await client.search("x")

    assert data == {"results": []}
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_timeout_retried_up_to_2_then_raises(monkeypatch):
    monkeypatch.setattr(client_module, "RETRY_BACKOFF_SECONDS", 0.0)
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        raise httpx.TimeoutException("simulated", request=request)

    client = TavilySearchClient(client=_client_with_handler(handler))
    with pytest.raises(TavilySearchError):
        await client.search("x")

    assert calls["count"] == 3  # 1 initial + 2 retries


@pytest.mark.asyncio
async def test_malformed_json_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    client = TavilySearchClient(client=_client_with_handler(handler))
    with pytest.raises(TavilySearchError):
        await client.search("x")


@pytest.mark.asyncio
async def test_credit_and_cost_tracking_accumulates():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    client = TavilySearchClient(client=_client_with_handler(handler))
    client.cost_per_credit_usd = 0.008

    await client.search("a")
    await client.search("b")

    assert client.request_count == 2
    assert client.credits_used == 2
    assert client.estimated_cost_usd == round(2 * 0.008, 6)


@pytest.mark.asyncio
async def test_budget_guard_stops_before_exceeding_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    client = TavilySearchClient(client=_client_with_handler(handler))
    client.max_requests_per_job = 2

    await client.search("a")
    await client.search("b")

    with pytest.raises(TavilySearchBudgetExceeded):
        await client.search("c")

    assert client.request_count == 2
    assert client.budget_exceeded is True
