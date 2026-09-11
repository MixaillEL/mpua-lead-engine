from datetime import datetime

from pydantic import BaseModel, Field


class CreateJobRequest(BaseModel):
    preset: str
    regions: list[str]
    target_count: int | None = None
    sources: dict[str, bool] = Field(default_factory=lambda: {"osm": True, "tavily": True})
    source_limits: dict[str, int] = Field(default_factory=lambda: {"osm": 100, "tavily": 20})
    website_enrichment: bool = True


class JobResponse(BaseModel):
    id: str
    status: str
    preset: str | None
    regions: list[str] | None
    sources_config: dict | None
    source_limits: dict | None
    website_enrichment: bool
    target_count: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None

    model_config = {"from_attributes": True}


class JobRunResponse(BaseModel):
    id: str
    job_id: str
    status: str
    current_stage: str
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    metrics: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RunJobResponse(BaseModel):
    job_run_id: str
    job_id: str
    status: str
    metrics: dict
    warnings: list[str]
