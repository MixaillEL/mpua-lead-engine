"""Tavily Search API HTTP client (Basic Search only — no generated answer,
no advanced search, no raw content, no crawl/extract). Tracks API
requests/credits used and enforces a hard per-job request budget.

Retry policy (kept simple — no generic retry framework):
    timeout/network error -> up to 2 retries
    HTTP 429               -> 1 retry with backoff
    HTTP 5xx                -> 1 retry
    HTTP 401/other 4xx      -> no retry (bad key / client error)
"""

import asyncio
import json
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger("mpua.sources.tavily_search")

USER_AGENT = "MPUA-Lead-Engine/0.1"
RETRY_BACKOFF_SECONDS = 1.5

# Basic Search costs 1 credit per request on Tavily's plans.
CREDITS_PER_BASIC_SEARCH = 1


class TavilySearchError(RuntimeError):
    """Raised for API/auth/quota failures that aren't retryable."""


class TavilySearchBudgetExceeded(RuntimeError):
    """Raised when a job would exceed TAVILY_MAX_REQUESTS_PER_JOB. Not an
    error — callers should treat this as a stop signal and use whatever
    results were already collected.
    """


class TavilySearchClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        self.api_key = settings.TAVILY_API_KEY
        self.api_url = settings.TAVILY_API_URL
        self.search_depth = settings.TAVILY_SEARCH_DEPTH
        self.max_results = settings.TAVILY_MAX_RESULTS
        self.timeout = settings.TAVILY_TIMEOUT
        self.max_requests_per_job = settings.TAVILY_MAX_REQUESTS_PER_JOB
        self.cost_per_credit_usd = settings.TAVILY_COST_PER_CREDIT_USD
        self._client = client
        self.request_count = 0
        self.credits_used = 0
        self.budget_exceeded = False

    @property
    def estimated_cost_usd(self) -> float:
        return round(self.credits_used * self.cost_per_credit_usd, 6)

    async def search(self, query: str, max_results: int | None = None) -> dict:
        if self.request_count >= self.max_requests_per_job:
            self.budget_exceeded = True
            raise TavilySearchBudgetExceeded(
                f"TAVILY_MAX_REQUESTS_PER_JOB ({self.max_requests_per_job}) reached"
            )

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        body = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": self.search_depth,  # "basic" only in v0.1
            "max_results": max_results or self.max_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }

        client_cm = self._client if self._client is not None else httpx.AsyncClient()
        owns_client = self._client is None

        try:
            attempt = 0
            max_retries = 2
            last_error: Exception | None = None

            while attempt <= max_retries:
                try:
                    response = await client_cm.post(
                        self.api_url, headers=headers, json=body, timeout=self.timeout
                    )
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
                    last_error = exc
                    attempt += 1
                    if attempt <= max_retries:
                        await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                        continue
                    raise TavilySearchError(f"Tavily Search request failed: {exc}") from exc

                if response.status_code == 401:
                    raise TavilySearchError("Tavily Search auth error: HTTP 401 (bad API key)")

                if response.status_code == 429 and attempt < 1:
                    attempt += 1
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS)
                    continue

                if response.status_code >= 500 and attempt < 1:
                    attempt += 1
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS)
                    continue

                if response.status_code >= 400:
                    raise TavilySearchError(f"Tavily Search returned HTTP {response.status_code}")

                self.request_count += 1
                self.credits_used += CREDITS_PER_BASIC_SEARCH

                try:
                    return response.json()
                except json.JSONDecodeError as exc:
                    raise TavilySearchError(f"Tavily Search returned invalid JSON: {exc}") from exc

            raise TavilySearchError(f"Tavily Search request failed after retries: {last_error}")
        finally:
            if owns_client:
                await client_cm.aclose()
