import pytest

from sources.mock.adapter import MockAdapter


@pytest.mark.asyncio
async def test_mock_adapter_returns_100_candidates():
    adapter = MockAdapter()
    candidates = await adapter.search(query="HVAC", region="Kyiv", limit=100)

    assert len(candidates) == 100
    assert all(c.name for c in candidates)
    names = {c.name for c in candidates}
    assert names == {f"Company {i:03d}" for i in range(1, 101)}


@pytest.mark.asyncio
async def test_mock_adapter_respects_limit():
    adapter = MockAdapter()
    candidates = await adapter.search(query="HVAC", region="Kyiv", limit=10)

    assert len(candidates) == 10


@pytest.mark.asyncio
async def test_mock_adapter_applies_region():
    adapter = MockAdapter()
    candidates = await adapter.search(query="HVAC", region="Lviv", limit=5)

    assert all(c.city == "Lviv" for c in candidates)
    assert all(c.raw_payload["region"] == "Lviv" for c in candidates)


@pytest.mark.asyncio
async def test_mock_adapter_fetch_details_not_supported():
    adapter = MockAdapter()
    candidates = await adapter.search(query="HVAC", limit=1)

    with pytest.raises(NotImplementedError):
        await adapter.fetch_details(candidates[0])
