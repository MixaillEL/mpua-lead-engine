from abc import ABC, abstractmethod

from app.models.source import SourceType
from sources.schemas import RawCandidate


class SourceAdapter(ABC):
    """Common contract every data source (Google Maps, Search, directories,
    mock data, ...) must implement. No scraping/network logic lives here —
    this is purely the interface concrete adapters plug into.
    """

    name: str
    source_type: SourceType
    supports_search: bool = True
    supports_details: bool = False
    default_limit: int = 100

    @abstractmethod
    async def search(
        self,
        query: str,
        region: str | None = None,
        limit: int = 100,
    ) -> list[RawCandidate]:
        """Return up to `limit` candidates matching `query` (and `region`)."""
        ...

    @abstractmethod
    async def fetch_details(
        self,
        candidate: RawCandidate,
    ) -> RawCandidate:
        """Enrich a single candidate with additional details. Adapters that
        don't support this should raise NotImplementedError and set
        supports_details = False.
        """
        ...
