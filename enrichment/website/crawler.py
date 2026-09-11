"""Bounded, same-domain website crawler: homepage + up to
WEBSITE_MAX_PAGES-1 discovered contact/about pages. No JS rendering, no
full-site traversal, no robots.txt fetching (documented debt — see
README), but skip-paths/tracking-param stripping/visited-set keep it from
looping or wandering off-domain.

Retry policy (kept intentionally simple, no generic retry framework):
    timeout/network error -> up to 2 retries
    HTTP 429               -> 1 retry with backoff
    HTTP 5xx                -> 1 retry
    HTTP 404 or other 4xx   -> no retry
"""

import asyncio
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from enrichment.website.extractor import extract_links
from enrichment.website.link_discovery import discover_contact_links, normalize_url
from enrichment.website.models import PageFetchResult
from enrichment.website.user_agent import get_user_agent

HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")

RETRY_BACKOFF_SECONDS = 1.5


class WebsiteCrawler:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        self.timeout = settings.WEBSITE_TIMEOUT
        self.max_pages = settings.WEBSITE_MAX_PAGES
        self.max_response_bytes = settings.WEBSITE_MAX_RESPONSE_BYTES
        self._client = client
        self._semaphore = asyncio.Semaphore(settings.WEBSITE_MAX_CONCURRENCY)
        self.requests_total = 0

    async def _do_request(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        self.requests_total += 1
        return await client.get(
            url,
            headers={"User-Agent": get_user_agent()},
            timeout=self.timeout,
            follow_redirects=True,
        )

    async def _fetch_with_retry(self, client: httpx.AsyncClient, url: str) -> PageFetchResult:
        attempt = 0
        max_network_retries = 2
        last_error: Exception | None = None

        while attempt <= max_network_retries:
            try:
                async with self._semaphore:
                    response = await self._do_request(client, url)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
                last_error = exc
                attempt += 1
                if attempt <= max_network_retries:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                    continue
                return PageFetchResult(url=url, status_code=None, html=None, error=str(exc))

            if response.status_code == 429 and attempt < 1:
                attempt += 1
                await asyncio.sleep(RETRY_BACKOFF_SECONDS)
                continue

            if response.status_code >= 500 and attempt < 1:
                attempt += 1
                await asyncio.sleep(RETRY_BACKOFF_SECONDS)
                continue

            return self._to_page_result(response)

        return PageFetchResult(url=url, status_code=None, html=None, error=str(last_error))

    def _to_page_result(self, response: httpx.Response) -> PageFetchResult:
        final_url = str(response.url)

        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if response.status_code >= 400:
            return PageFetchResult(
                url=final_url, status_code=response.status_code, html=None, error=f"HTTP {response.status_code}"
            )

        if content_type and content_type not in HTML_CONTENT_TYPES:
            return PageFetchResult(
                url=final_url,
                status_code=response.status_code,
                html=None,
                error=f"non-HTML content-type: {content_type}",
            )

        content = response.content
        if len(content) > self.max_response_bytes:
            content = content[: self.max_response_bytes]

        try:
            html = content.decode(response.encoding or "utf-8", errors="replace")
        except (LookupError, UnicodeDecodeError):
            html = content.decode("utf-8", errors="replace")

        return PageFetchResult(url=final_url, status_code=response.status_code, html=html, error=None)

    async def crawl(self, root_url: str) -> list[PageFetchResult]:
        root_domain = (urlparse(root_url).hostname or "").lower()
        root_domain = root_domain[4:] if root_domain.startswith("www.") else root_domain

        client_cm = self._client if self._client is not None else httpx.AsyncClient()
        owns_client = self._client is None

        pages: list[PageFetchResult] = []
        visited: set[str] = {normalize_url(root_url)}

        try:
            homepage = await self._fetch_with_retry(client_cm, root_url)
            pages.append(homepage)

            if homepage.html:
                links = extract_links(homepage.html)
                contact_urls = discover_contact_links(links, base_url=homepage.url, root_domain=root_domain)

                for url in contact_urls:
                    if len(pages) >= self.max_pages:
                        break
                    normalized = normalize_url(url)
                    if normalized in visited:
                        continue
                    visited.add(normalized)

                    page = await self._fetch_with_retry(client_cm, url)
                    pages.append(page)
        finally:
            if owns_client:
                await client_cm.aclose()

        return pages
