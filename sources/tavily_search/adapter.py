"""Tavily Web Search discovery adapter — implements the existing
SourceAdapter contract unchanged. Basic Search only, used solely to
discover official company websites (never rating/reviews/generated
answers).
"""

import logging

from app.models.source import SourceType
from sources.base import SourceAdapter
from sources.schemas import RawCandidate
from sources.tavily_search.client import TavilySearchBudgetExceeded, TavilySearchClient, TavilySearchError
from sources.tavily_search.parser import (
    TavilySearchResult,
    dedupe_by_domain,
    filter_relevant,
    parse_response,
    result_to_candidate,
)
from sources.tavily_search.query_builder import build_query_variants

logger = logging.getLogger("mpua.sources.tavily_search.adapter")


class TavilySearchAdapter(SourceAdapter):
    name = "Tavily Web Search"
    source_type = SourceType.web_search
    supports_search = True
    supports_details = False
    default_limit = 20

    def __init__(self, country: str = "UA", client: TavilySearchClient | None = None) -> None:
        self.country = country
        self._client = client or TavilySearchClient()

        # Populated after each search() call for cost-tracking/reporting.
        self.last_api_requests = 0
        self.last_credits_used = 0
        self.last_estimated_cost_usd = 0.0
        self.last_results_received = 0
        self.last_unique_domains = 0
        self.last_budget_exceeded = False

    async def search(
        self,
        query: str,
        region: str | None = None,
        limit: int = 20,
    ) -> list[RawCandidate]:
        variants = build_query_variants(query, region)

        all_results: list[TavilySearchResult] = []
        budget_exceeded = False

        for variant in variants:
            try:
                data = await self._client.search(variant, max_results=max(limit, 10))
            except TavilySearchBudgetExceeded:
                budget_exceeded = True
                break
            except TavilySearchError:
                logger.error(
                    "tavily search adapter: request failed",
                    extra={"query": variant, "region": region},
                    exc_info=True,
                )
                raise

            all_results.extend(parse_response(data, query=variant))

        self.last_results_received = len(all_results)

        deduped = dedupe_by_domain(all_results)
        self.last_unique_domains = len(deduped)

        relevant = filter_relevant(deduped)

        candidates = [
            result_to_candidate(r, country=self.country, region=region) for r in relevant[:limit]
        ]

        self.last_api_requests = self._client.request_count
        self.last_credits_used = self._client.credits_used
        self.last_estimated_cost_usd = self._client.estimated_cost_usd
        self.last_budget_exceeded = budget_exceeded or self._client.budget_exceeded

        return candidates

    async def fetch_details(self, candidate: RawCandidate) -> RawCandidate:
        raise NotImplementedError("TavilySearchAdapter does not support fetch_details in v0.1")
