from pathlib import Path

import httpx
import pytest

import enrichment.website.crawler as crawler_module
from enrichment.website.crawler import WebsiteCrawler

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_homepage_and_contact_pages_are_fetched():
    html_a = _load("website_a_complete.html")

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/":
            return httpx.Response(200, content=html_a.encode(), headers={"content-type": "text/html"})
        if path in ("/contacts", "/about"):
            return httpx.Response(200, content=b"<html><body>ok</body></html>", headers={"content-type": "text/html"})
        return httpx.Response(404)

    crawler = WebsiteCrawler(client=_client(handler))
    pages = await crawler.crawl("https://example.com/")

    urls = {p.url for p in pages}
    assert any(u.endswith("/contacts") for u in urls)
    assert any(u.rstrip("/") == "https://example.com" for u in urls)


@pytest.mark.asyncio
async def test_page_limit_is_respected():
    def handler(request: httpx.Request) -> httpx.Response:
        html = (
            "<html><body>"
            '<a href="/contacts">contacts</a>'
            '<a href="/about">about</a>'
            '<a href="/kontakty">kontakty</a>'
            "</body></html>"
        )
        return httpx.Response(200, content=html.encode(), headers={"content-type": "text/html"})

    crawler = WebsiteCrawler(client=_client(handler))
    crawler.max_pages = 2
    pages = await crawler.crawl("https://example.com/")

    assert len(pages) <= 2


@pytest.mark.asyncio
async def test_404_is_not_retried():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(404)

    crawler = WebsiteCrawler(client=_client(handler))
    pages = await crawler.crawl("https://example.com/")

    assert pages[0].status_code == 404
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_timeout_is_retried_then_reported(monkeypatch):
    monkeypatch.setattr(crawler_module, "RETRY_BACKOFF_SECONDS", 0.0)
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        raise httpx.TimeoutException("simulated timeout", request=request)

    crawler = WebsiteCrawler(client=_client(handler))
    pages = await crawler.crawl("https://example.com/")

    assert pages[0].html is None
    assert pages[0].error is not None
    assert calls["count"] == 3  # 1 initial + 2 retries


@pytest.mark.asyncio
async def test_429_gets_one_retry(monkeypatch):
    monkeypatch.setattr(crawler_module, "RETRY_BACKOFF_SECONDS", 0.0)
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429)
        return httpx.Response(200, content=b"<html></html>", headers={"content-type": "text/html"})

    crawler = WebsiteCrawler(client=_client(handler))
    pages = await crawler.crawl("https://example.com/")

    assert pages[0].status_code == 200
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_redirect_is_followed_and_final_url_recorded():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.com":
            return httpx.Response(301, headers={"location": "https://www.example.com/"})
        return httpx.Response(200, content=b"<html></html>", headers={"content-type": "text/html"})

    crawler = WebsiteCrawler(client=_client(handler))
    pages = await crawler.crawl("https://example.com/")

    assert pages[0].url == "https://www.example.com/"


@pytest.mark.asyncio
async def test_binary_content_is_ignored():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-1.4 binary", headers={"content-type": "application/pdf"})

    crawler = WebsiteCrawler(client=_client(handler))
    pages = await crawler.crawl("https://example.com/")

    assert pages[0].html is None
    assert "non-HTML" in (pages[0].error or "")


@pytest.mark.asyncio
async def test_oversized_response_is_truncated_not_crashed():
    big_html = "<html><body>" + ("x" * 200) + "</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big_html.encode(), headers={"content-type": "text/html"})

    crawler = WebsiteCrawler(client=_client(handler))
    crawler.max_response_bytes = 50
    pages = await crawler.crawl("https://example.com/")

    assert pages[0].html is not None
    assert len(pages[0].html.encode()) <= 50


@pytest.mark.asyncio
async def test_external_domain_links_are_not_crawled():
    html_d = _load("website_d_external_links.html")
    requested_paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(str(request.url))
        if request.url.path == "/":
            return httpx.Response(200, content=html_d.encode(), headers={"content-type": "text/html"})
        return httpx.Response(200, content=b"<html></html>", headers={"content-type": "text/html"})

    crawler = WebsiteCrawler(client=_client(handler))
    await crawler.crawl("https://example.com/")

    assert all("partner-site.com" not in url for url in requested_paths)
