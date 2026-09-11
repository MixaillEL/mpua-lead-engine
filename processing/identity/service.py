"""Main identity-resolution entrypoints.

    NormalizedCandidate
    -> load possible matches (indexed lookups only)
    -> evaluate identity signals
    -> NEW / MATCH / REVIEW
    -> persist (NEW: create Company; MATCH: merge; REVIEW: no persistence)

REVIEW policy (MLE-005 v0.1, "Variant A"): a REVIEW decision never creates
or merges a Company. This keeps the identity graph clean — a missed
duplicate can be reviewed and merged later; an incorrectly auto-merged
Company is much harder to undo safely.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from processing.identity.matcher import find_scored_matches
from processing.identity.merger import create_company, merge_into_company
from processing.identity.models import Decision, IdentityResult
from processing.identity.resolver import resolve_decision
from processing.normalization.models import NormalizedCandidate

logger = logging.getLogger("mpua.processing.identity")


def resolve_and_persist_candidate(
    db: Session,
    candidate: NormalizedCandidate,
    source_id: str | None = None,
) -> tuple[IdentityResult, int]:
    """Returns (IdentityResult, contacts_added)."""

    source_type = candidate.source_type.value if candidate.source_type else None

    scored_matches = find_scored_matches(
        db, candidate, source_type=source_type, external_id=candidate.external_id
    )
    decision = resolve_decision(scored_matches)

    if decision.decision == Decision.NEW:
        company, added = create_company(db, candidate, source_id)
        return (
            IdentityResult(
                decision=Decision.NEW,
                company_id=company.id,
                score=decision.score,
                created=True,
                merged=False,
                signals=decision.signals,
            ),
            added,
        )

    if decision.decision == Decision.MATCH:
        company, added = merge_into_company(db, decision.company_id, candidate, source_id)
        return (
            IdentityResult(
                decision=Decision.MATCH,
                company_id=company.id,
                score=decision.score,
                created=False,
                merged=True,
                signals=decision.signals,
            ),
            added,
        )

    # REVIEW: no persistence, per policy above.
    return (
        IdentityResult(
            decision=Decision.REVIEW,
            company_id=decision.company_id,
            score=decision.score,
            created=False,
            merged=False,
            signals=decision.signals,
        ),
        0,
    )


@dataclass
class ResolutionStats:
    received: int
    new: int = 0
    matched: int = 0
    review: int = 0
    failed: int = 0
    companies_created: int = 0
    contacts_added: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "received": self.received,
            "new": self.new,
            "matched": self.matched,
            "review": self.review,
            "failed": self.failed,
            "companies_created": self.companies_created,
            "contacts_added": self.contacts_added,
        }


def resolve_candidates(
    db: Session,
    candidates: list[tuple[NormalizedCandidate, str | None]],
) -> tuple[list[IdentityResult], ResolutionStats]:
    """`candidates` is a list of (NormalizedCandidate, source_id) pairs.
    One bad candidate is isolated (SAVEPOINT) and does not fail the batch.
    """

    stats = ResolutionStats(received=len(candidates))
    results: list[IdentityResult] = []

    for candidate, source_id in candidates:
        try:
            with db.begin_nested():
                result, added = resolve_and_persist_candidate(db, candidate, source_id)
            results.append(result)
            stats.contacts_added += added

            if result.decision == Decision.NEW:
                stats.new += 1
                stats.companies_created += 1
            elif result.decision == Decision.MATCH:
                stats.matched += 1
            else:
                stats.review += 1

        except Exception as exc:  # noqa: BLE001 - isolate one bad candidate
            stats.failed += 1
            stats.errors.append(str(exc))
            logger.warning(
                "identity resolution: failed to resolve candidate",
                extra={"external_id": candidate.external_id, "error": str(exc)},
            )

    db.commit()
    return results, stats
