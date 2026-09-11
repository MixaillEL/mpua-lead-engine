from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.source import SourceType


class RawCandidate(BaseModel):
    """Transport model produced by a SourceAdapter, independent of the ORM.

    Extra fields are allowed so new attributes can be added later without
    breaking existing adapters or the persistence pipeline.
    """

    model_config = ConfigDict(extra="allow")

    external_id: str | None = None
    name: str
    category: str | None = None
    description: str | None = None

    country: str | None = None
    region: str | None = None
    city: str | None = None
    raw_address: str | None = None

    phone: str | None = None
    website: str | None = None
    email: str | None = None

    rating: float | None = None
    reviews_count: int | None = None

    source_type: SourceType
    source_url: str | None = None

    raw_payload: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, value: str) -> str:
        if value is None or not value.strip():
            raise ValueError("name must not be empty")
        return value
