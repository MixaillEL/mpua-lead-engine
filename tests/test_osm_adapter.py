import json

import httpx
import pytest

import sources.osm.adapter as osm_adapter_module
from sources.osm.adapter import OpenStreetMapAdapter, OverpassRequestError


def _client_with_handler(handler) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


@pytest.mark.asyncio
async def test_empty_result_is_not_an_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"elements": []})

    client = _client_with_handler(handler)
    adapter = OpenStreetMapAdapter(client=client)

    candidates = await adapter.search(query="dentist", region="Dnipro", limit=20)

    assert candidates == []


@pytest.mark.asyncio
async def test_invalid_json_is_handled(monkeypatch):
    monkeypatch.setattr(osm_adapter_module, "RETRY_BACKOFF_SECONDS", 0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all")

    client = _client_with_handler(handler)
    adapter = OpenStreetMapAdapter(client=client)

    with pytest.raises(OverpassRequestError):
        await adapter.search(query="dentist", region="Dnipro", limit=20)


@pytest.mark.asyncio
async def test_timeout_is_handled(monkeypatch):
    monkeypatch.setattr(osm_adapter_module, "RETRY_BACKOFF_SECONDS", 0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout", request=request)

    client = _client_with_handler(handler)
    adapter = OpenStreetMapAdapter(client=client)

    with pytest.raises(OverpassRequestError):
        await adapter.search(query="dentist", region="Dnipro", limit=20)


@pytest.mark.asyncio
async def test_server_error_is_handled(monkeypatch):
    monkeypatch.setattr(osm_adapter_module, "RETRY_BACKOFF_SECONDS", 0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = _client_with_handler(handler)
    adapter = OpenStreetMapAdapter(client=client)

    with pytest.raises(OverpassRequestError):
        await adapter.search(query="dentist", region="Dnipro", limit=20)


@pytest.mark.asyncio
async def test_search_parses_fixture_and_applies_limit(monkeypatch):
    with open("tests/fixtures/osm_overpass_response.json", encoding="utf-8") as f:
        fixture = json.load(f)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture)

    client = _client_with_handler(handler)
    adapter = OpenStreetMapAdapter(client=client)

    candidates = await adapter.search(query="dentist", region="Dnipro", limit=2)

    assert len(candidates) == 2


@pytest.mark.asyncio
async def test_search_requires_region():
    adapter = OpenStreetMapAdapter()

    with pytest.raises(ValueError):
        await adapter.search(query="dentist", region=None, limit=10)


@pytest.mark.asyncio
async def test_unsupported_preset_raises():
    adapter = OpenStreetMapAdapter()

    with pytest.raises(ValueError):
        await adapter.search(query="hvac", region="Dnipro", limit=10)


@pytest.mark.asyncio
async def test_fetch_details_not_supported():
    adapter = OpenStreetMapAdapter()

    with pytest.raises(NotImplementedError):
        await adapter.fetch_details(None)
