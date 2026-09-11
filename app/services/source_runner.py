import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.job import Job
from app.models.raw_record import RawRecord
from app.models.source import Source
from sources.base import SourceAdapter
from sources.schemas import RawCandidate

logger = logging.getLogger("mpua.source_runner")


@dataclass
class SourceRunStats:
    requested: int
    received: int = 0
    saved: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "requested": self.requested,
            "received": self.received,
            "saved": self.saved,
            "failed": self.failed,
        }


def persist_candidate(db: Session, job_id: str, candidate: RawCandidate) -> RawRecord:
    """RawCandidate -> Source -> RawRecord. Never creates a Company."""

    source = Source(
        source_type=candidate.source_type,
        source_url=candidate.source_url,
        external_id=candidate.external_id,
        job_id=job_id,
    )
    db.add(source)
    db.flush()

    # Store the adapter's original payload verbatim; fall back to a full
    # dump of the candidate if the adapter didn't provide one, so nothing
    # is silently lost.
    payload = candidate.raw_payload if candidate.raw_payload is not None else candidate.model_dump(mode="json")

    raw_record = RawRecord(
        job_id=job_id,
        source_id=source.id,
        raw_payload=payload,
        processing_status="pending",
    )
    db.add(raw_record)
    db.flush()

    return raw_record


async def run_source_search(
    db: Session,
    job_id: str,
    adapter: SourceAdapter,
    query: str,
    region: str | None = None,
    limit: int = 100,
) -> dict:
    job = db.get(Job, job_id)
    if job is None:
        raise ValueError(f"Job {job_id} not found")

    started = time.monotonic()
    stats = SourceRunStats(requested=limit)

    candidates = await adapter.search(query=query, region=region, limit=limit)
    stats.received = len(candidates)

    for candidate in candidates:
        try:
            # Each candidate gets its own SAVEPOINT so a single bad record
            # can be rolled back without discarding the rest of the batch
            # or any transaction the caller already has open.
            with db.begin_nested():
                persist_candidate(db, job_id=job.id, candidate=candidate)
            stats.saved += 1
        except Exception as exc:  # noqa: BLE001 - isolate a bad candidate, keep the batch going
            stats.failed += 1
            stats.errors.append(str(exc))
            logger.warning(
                "source_runner: failed to persist candidate",
                extra={"job_id": job_id, "adapter": adapter.name, "error": str(exc)},
            )

    db.commit()

    duration = time.monotonic() - started
    logger.info(
        "source_runner: search finished",
        extra={
            "job_id": job_id,
            "adapter": adapter.name,
            "query": query,
            "region": region,
            "requested": stats.requested,
            "received": stats.received,
            "saved": stats.saved,
            "failed": stats.failed,
            "duration": round(duration, 4),
        },
    )

    return stats.as_dict()
