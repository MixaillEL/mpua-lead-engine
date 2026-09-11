"""Tavily API JSON -> TavilySearchResult -> RawCandidate. Pure parsing/
transformation, no network calls.

`content` (Tavily's snippet) is preserved only inside raw_payload/source
context — it is never written into RawCandidate.description or
Company.description, since a search snippet can be stale and is not a
verified business fact.
"""

import hashlib
from dataclasses import dataclass
from typing import Any

from app.models.source import SourceType
from sources.schemas import RawCandidate
from sources.tavily_search.filters import clean_title, get_domain, is_relevant_result


@dataclass
class TavilySearchResult:
    title: str
    url: str
    content: str | None
    score: float | None
    rank: int
    query: str


def parse_response(data: dict[str, Any], query: str) -> list[TavilySearchResult]:
    raw_results = data.get("results") or []

    results = []
    for rank, item in enumerate(raw_results):
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        if not title or not url:
            continue

        results.append(
            TavilySearchResult(
                title=title,
                url=url,
                content=item.get("content"),
                score=item.get("score"),
                rank=rank,
                query=query,
            )
        )

    return results


def dedupe_by_domain(results: list[TavilySearchResult]) -> list[TavilySearchResult]:
    """example.com, example.com/contact, example.com/about -> keep the
    first (highest-ranked) occurrence per normalized domain.
    """

    seen_domains: set[str] = set()
    deduped: list[TavilySearchResult] = []

    for result in results:
        domain = get_domain(result.url)
        if not domain or domain in seen_domains:
            continue
        seen_domains.add(domain)
        deduped.append(result)

    return deduped


def filter_relevant(results: list[TavilySearchResult]) -> list[TavilySearchResult]:
    return [r for r in results if is_relevant_result(r.title, r.url)]


def result_to_candidate(result: TavilySearchResult, country: str | None, region: str | None) -> RawCandidate:
    domain = get_domain(result.url) or result.url
    external_id = "tavily:" + hashlib.sha256(domain.encode("utf-8")).hexdigest()[:32]

    return RawCandidate(
        external_id=external_id,
        name=clean_title(result.title),
        description=None,  # snippet is raw context only, see module docstring
        country=country,
        region=region,
        website=result.url,
        source_type=SourceType.web_search,
        source_url=result.url,
        raw_payload={
            "title": result.title,
            "url": result.url,
            "content": result.content,
            "score": result.score,
            "rank": result.rank,
            "query": result.query,
        },
    )
