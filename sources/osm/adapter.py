"""OpenStreetMap / Overpass discovery adapter.

Public Overpass endpoint = development / validation source.
Do not point production/high-volume traffic at it — concurrency for this
adapter is intentionally capped at 1 in-flight request.
"""

import asyncio
import json
import logging

import httpx

from app.core.config import get_settings
from app.models.source import SourceType
from sources.base import SourceAdapter
from sources.osm.parser import parse_elements
from sources.osm.query_builder import build_preset_query
from sources.osm.tag_mapping import get_preset
from sources.schemas import RawCandidate

logger = logging.getLogger("mpua.sources.osm.adapter")

USER_AGENT = "MPUA-Lead-Engine/0.1"

MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 2.0


class OverpassRequestError(RuntimeError):
    """Raised when the Overpass API can't be queried successfully."""


class OpenStreetMapAdapter(SourceAdapter):
    name = "OpenStreetMap / Overpass"
    source_type = SourceType.openstreetmap
    supports_search = True
    supports_details = False
    default_limit = 100

    # Overpass is a shared public service; never fan out concurrent
    # requests from this adapter.
    _semaphore = asyncio.Semaphore(1)

    def __init__(self, country: str = "UA", client: httpx.AsyncClient | None = None) -> None:
        self.country = country
        self._client = client
        settings = get_settings()
        self.api_url = settings.OVERPASS_API_URL
        self.timeout = settings.OVERPASS_TIMEOUT

    async def _post_query(self, query: str) -> dict:
        headers = {"User-Agent": USER_AGENT}

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                async with self._semaphore:
                    if self._client is not None:
                        response = await self._client.post(
                            self.api_url, data={"data": query}, headers=headers, timeout=self.timeout
                        )
                    else:
                        async with httpx.AsyncClient() as client:
                            response = await client.post(
                                self.api_url, data={"data": query}, headers=headers, timeout=self.timeout
                            )

                if response.status_code == 429 or response.status_code >= 500:
                    raise OverpassRequestError(
                        f"Overpass returned HTTP {response.status_code}"
                    )

                response.raise_for_status()

                try:
                    return response.json()
                except json.JSONDecodeError as exc:
                    raise OverpassRequestError(f"Overpass returned invalid JSON: {exc}") from exc

            except (httpx.TimeoutException, httpx.HTTPError, OverpassRequestError) as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "osm adapter: request failed, retrying",
                        extra={"attempt": attempt + 1, "error": str(exc)},
                    )
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                    continue
                break

        raise OverpassRequestError(f"Overpass request failed after retries: {last_error}") from last_error

    async def search(
        self,
        query: str,
        region: str | None = None,
        limit: int = 100,
    ) -> list[RawCandidate]:
        if not region:
            raise ValueError("OpenStreetMapAdapter.search requires `region` (city name)")

        preset = get_preset(query)

        overpass_query = build_preset_query(
            preset=preset,
            city=region,
            country=self.country,
            timeout=self.timeout,
            # ask Overpass for a bit of headroom over `limit`; the parser
            # still enforces the hard client-side cap.
            output_limit=max(limit * 2, limit),
        )

        try:
            data = await self._post_query(overpass_query)
        except OverpassRequestError:
            logger.error(
                "osm adapter: search failed",
                extra={"preset": query, "region": region},
                exc_info=True,
            )
            raise

        elements = data.get("elements", [])

        return parse_elements(
            elements,
            preset=preset,
            country=self.country,
            region=region,
            city=region,
            limit=limit,
        )

    async def fetch_details(self, candidate: RawCandidate) -> RawCandidate:
        raise NotImplementedError("OpenStreetMapAdapter does not support fetch_details in v0.1")
