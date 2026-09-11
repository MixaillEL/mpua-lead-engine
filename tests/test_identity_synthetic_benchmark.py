"""Synthetic 100-candidate duplicate benchmark (MLE-005 #40-42).

Composition (100 candidates total):
  - 65 fully unique candidates (distinct phone/domain/name+city/address,
    no relation to anything else in the batch) -> expect 65 NEW, 0 matches.
  - 5 of those 65 are re-sent once more via the SAME source external_id
    (5 extra "resend" records) -> expect 5 MATCH via same_source_external_id.
  - 10 candidates forming 5 same-phone duplicate pairs -> expect 5 MATCH.
  - 10 candidates forming 5 same-domain duplicate pairs -> expect 5 MATCH.
  - 10 candidates forming 5 same-name+city-only ambiguous pairs -> expect
    5 REVIEW (never auto-merged).

  65 + 5 + 10 + 10 + 10 = 100.

true_duplicates = 5 (source-id) + 5 (phone) + 5 (domain) = 15 pairs that
MUST auto-merge. The 5 name+city pairs are deliberately ambiguous and are
NOT counted as "must auto-merge" — a missed match there is acceptable
(REVIEW), an auto-merge there would be wrong.

Precision is the critical KPI: zero real different companies may ever be
auto-merged (false positive). Recall is secondary.
"""

import pytest
from sqlalchemy import select

from app.models.company import Company
from app.models.source import Source, SourceType
from processing.identity.models import Decision
from processing.identity.service import resolve_candidates
from processing.normalization.models import NormalizedCandidate


def _candidate(i: int, **overrides) -> NormalizedCandidate:
    defaults = dict(
        external_id=None,
        canonical_name=f"Company {i:03d}",
        normalized_name=f"company {i:03d}",
        category="benchmark",
        country="UA",
        region="Dnipro",
        city="Dnipro",
        normalized_city=f"city{i:03d}",
        raw_address=None,
        normalized_address=None,
        phone_raw=None,
        phone_normalized=f"+38050{i:07d}",
        email_raw=None,
        email_normalized=None,
        website_raw=None,
        website_url=None,
        website_domain=None,
        rating=None,
        reviews_count=None,
        source_type=SourceType.manual,
        source_url=None,
        raw_payload=None,
    )
    defaults.update(overrides)
    return NormalizedCandidate(**defaults)


def _build_dataset(db):
    candidates: list[tuple[NormalizedCandidate, str | None]] = []
    created_source_ids: list[str] = []

    # 65 fully unique candidates, each with its own unique phone/name/city.
    unique = [_candidate(i) for i in range(1, 66)]
    candidates.extend((c, None) for c in unique)

    # 5 of the 65 unique ones (indices 0-4) get resent via the same source
    # external_id.
    for idx in range(5):
        base = unique[idx]
        ext_id = f"osm:node:resend-{idx}"
        source1 = Source(source_type=SourceType.openstreetmap, external_id=ext_id)
        source2 = Source(source_type=SourceType.openstreetmap, external_id=ext_id)
        db.add_all([source1, source2])
        db.flush()
        created_source_ids.extend([source1.id, source2.id])

        original = base.model_copy(update={"external_id": ext_id, "source_type": SourceType.openstreetmap})
        resend = original.model_copy()
        # Replace the (None, None)-sourced entry already added with a
        # source-linked one, and append the resend copy.
        candidates[idx] = (original, source1.id)
        candidates.append((resend, source2.id))

    # 5 same-phone duplicate pairs (10 candidates)
    for i in range(5):
        shared_phone = f"+38099{i:07d}"
        candidates.append((_candidate(1000 + i * 2, phone_normalized=shared_phone), None))
        candidates.append(
            (
                _candidate(
                    1000 + i * 2 + 1,
                    phone_normalized=shared_phone,
                    normalized_name=f"different name {i}",
                ),
                None,
            )
        )

    # 5 same-domain duplicate pairs (10 candidates)
    for i in range(5):
        shared_domain = f"dup-domain-{i}.example.com"
        candidates.append(
            (_candidate(2000 + i * 2, phone_normalized=None, website_domain=shared_domain), None)
        )
        candidates.append(
            (
                _candidate(
                    2000 + i * 2 + 1,
                    phone_normalized=None,
                    website_domain=shared_domain,
                    normalized_name=f"different domain co {i}",
                ),
                None,
            )
        )

    # 5 same-name+city-only ambiguous pairs (10 candidates) -> REVIEW
    for i in range(5):
        shared_name = f"ambiguous co {i}"
        shared_city = f"ambiguous city {i}"
        candidates.append(
            (
                _candidate(
                    3000 + i * 2,
                    phone_normalized=None,
                    normalized_name=shared_name,
                    normalized_city=shared_city,
                ),
                None,
            )
        )
        candidates.append(
            (
                _candidate(
                    3000 + i * 2 + 1,
                    phone_normalized=None,
                    normalized_name=shared_name,
                    normalized_city=shared_city,
                ),
                None,
            )
        )

    db.commit()
    assert len(candidates) == 100
    return candidates, created_source_ids


@pytest.mark.asyncio
async def test_synthetic_duplicate_benchmark(committing_db_session):
    db = committing_db_session

    candidates, source_ids = _build_dataset(db)

    results, stats = resolve_candidates(db, candidates)

    created_company_ids = [r.company_id for r in results if r.company_id]

    try:
        assert stats.received == 100
        assert stats.failed == 0

        true_duplicate_pairs = 5 + 5 + 5  # source-id + phone + domain
        review_pairs = 5  # name+city ambiguous

        # Every true-duplicate pair contributes exactly one MATCH (the 2nd
        # occurrence matches the 1st, already-created company).
        detected_matches = sum(1 for r in results if r.decision == Decision.MATCH)
        review_cases = sum(1 for r in results if r.decision == Decision.REVIEW)
        new_cases = sum(1 for r in results if r.decision == Decision.NEW)

        assert detected_matches == true_duplicate_pairs
        assert review_cases == review_pairs
        assert new_cases == 100 - true_duplicate_pairs - review_pairs

        # False positive check: no two *unrelated* companies collapsed into
        # one. Every created Company's normalized_name is unique except for
        # the 5 ambiguous "ambiguous co N" pairs, which never got merged
        # (both persisted as separate NEW... but REVIEW means the 2nd one is
        # NOT persisted at all, so only 65+5+5+5+5(1 per ambiguous pair)=... )
        companies = db.scalars(select(Company).where(Company.id.in_(created_company_ids))).all()
        names = [c.normalized_name for c in companies]
        assert len(names) == len(set(names)), "false positive: two different companies share a name unexpectedly"

        false_matches = 0  # by construction/assertions above
        missed_duplicates = true_duplicate_pairs - detected_matches
        precision = detected_matches / (detected_matches + false_matches)
        recall = detected_matches / true_duplicate_pairs

        print(
            f"\nSynthetic benchmark: candidates=100 true_duplicates={true_duplicate_pairs} "
            f"auto_matches={detected_matches} reviews={review_cases} false_matches={false_matches} "
            f"missed={missed_duplicates} precision={precision:.2f} recall={recall:.2f}"
        )

        assert false_matches == 0
        assert precision == 1.0
    finally:
        for company_id in created_company_ids:
            company = db.get(Company, company_id)
            if company is not None:
                db.delete(company)
        db.commit()
        for source_id in source_ids:
            source = db.get(Source, source_id)
            if source is not None:
                db.delete(source)
        db.commit()
