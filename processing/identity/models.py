import enum

from pydantic import BaseModel


class Decision(str, enum.Enum):
    NEW = "NEW"
    MATCH = "MATCH"
    REVIEW = "REVIEW"


class IdentityDecision(BaseModel):
    """Pure decision output of the matcher/resolver — no persistence side
    effects, no DB access.
    """

    decision: Decision
    company_id: str | None = None
    score: int
    signals: list[str] = []
    reason: str


class IdentityResult(BaseModel):
    """What actually happened when resolve_and_persist_candidate() ran."""

    decision: Decision
    company_id: str | None = None
    score: int
    created: bool = False
    merged: bool = False
    signals: list[str] = []
