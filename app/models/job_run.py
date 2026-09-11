import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.job import JobStatus
from db.base import Base


class PipelineStage(str, enum.Enum):
    created = "CREATED"
    discovery_osm = "DISCOVERY_OSM"
    discovery_web_search = "DISCOVERY_WEB_SEARCH"
    normalization = "NORMALIZATION"
    identity_resolution = "IDENTITY_RESOLUTION"
    website_enrichment = "WEBSITE_ENRICHMENT"
    finalizing = "FINALIZING"
    completed = "COMPLETED"
    failed = "FAILED"
    cancelled = "CANCELLED"


class JobRun(Base):
    """One concrete execution of a Job specification. Job = spec,
    JobRun = a run of it — a Job can be run repeatedly, each run gets its
    own history/metrics/audit trail.
    """

    __tablename__ = "job_runs"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)

    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=20), nullable=False, default=JobStatus.created
    )
    current_stage: Mapped[PipelineStage] = mapped_column(
        Enum(PipelineStage, native_enum=False, length=30), nullable=False, default=PipelineStage.created
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    job: Mapped["Job"] = relationship("Job", back_populates="runs")
    stage_runs: Mapped[list["JobStageRun"]] = relationship(
        "JobStageRun", back_populates="job_run", cascade="all, delete-orphan"
    )
