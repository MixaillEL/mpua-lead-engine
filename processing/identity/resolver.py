"""Applies the MLE-005 scoring policy (see signals.py) to the best scored
match and turns it into an IdentityDecision. Pure function — no DB access,
no persistence.
"""

from processing.identity.models import Decision, IdentityDecision
from processing.identity.signals import MatchCandidate

MATCH_THRESHOLD = 90
REVIEW_THRESHOLD = 60


def resolve_decision(
    scored_matches: list[tuple[MatchCandidate, int, list[str]]],
) -> IdentityDecision:
    if not scored_matches:
        return IdentityDecision(
            decision=Decision.NEW,
            company_id=None,
            score=0,
            signals=[],
            reason="No matching identity signals against any existing company",
        )

    best_match, score, signals = scored_matches[0]

    if score >= MATCH_THRESHOLD:
        return IdentityDecision(
            decision=Decision.MATCH,
            company_id=best_match.company_id,
            score=score,
            signals=signals,
            reason=f"Score {score} >= {MATCH_THRESHOLD}: {', '.join(signals)}",
        )

    if score >= REVIEW_THRESHOLD:
        return IdentityDecision(
            decision=Decision.REVIEW,
            company_id=best_match.company_id,
            score=score,
            signals=signals,
            reason=(
                f"Score {score} in review range [{REVIEW_THRESHOLD}, {MATCH_THRESHOLD}): "
                f"{', '.join(signals)} — not strong enough to auto-merge"
            ),
        )

    return IdentityDecision(
        decision=Decision.NEW,
        company_id=None,
        score=score,
        signals=signals,
        reason=f"Score {score} < {REVIEW_THRESHOLD}: signals too weak to associate with an existing company",
    )
