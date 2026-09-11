from pydantic import BaseModel


class MockSearchRequest(BaseModel):
    job_id: str
    query: str
    region: str | None = None
    limit: int = 100


class MockSearchResponse(BaseModel):
    requested: int
    received: int
    saved: int
    failed: int
