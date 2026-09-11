from app.models.source import SourceType
from sources.base import SourceAdapter
from sources.schemas import RawCandidate


class MockAdapter(SourceAdapter):
    """Deterministic in-memory adapter for testing the pipeline without any
    real network/scraping dependency.
    """

    name = "mock"
    source_type = SourceType.manual
    supports_search = True
    supports_details = False
    default_limit = 100

    async def search(
        self,
        query: str,
        region: str | None = None,
        limit: int = 100,
    ) -> list[RawCandidate]:
        count = min(limit, self.default_limit) if limit else self.default_limit
        candidates: list[RawCandidate] = []

        for i in range(1, count + 1):
            index = f"{i:03d}"
            external_id = f"mock-{index}"
            candidates.append(
                RawCandidate(
                    external_id=external_id,
                    name=f"Company {index}",
                    category="HVAC",
                    city=region,
                    phone=f"+38044{i:07d}",
                    website=f"https://company{index}.example.com",
                    rating=round(3.5 + (i % 15) / 10, 1),
                    reviews_count=i * 3,
                    source_type=self.source_type,
                    source_url=f"https://mock.local/company/{external_id}",
                    raw_payload={
                        "query": query,
                        "region": region,
                        "external_id": external_id,
                        "name": f"Company {index}",
                    },
                )
            )

        return candidates

    async def fetch_details(self, candidate: RawCandidate) -> RawCandidate:
        raise NotImplementedError("MockAdapter does not support fetch_details")
