import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.job_run import PipelineStage
from db.base import Base


class StageStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class JobStageRun(Base):
    __tablename__ = "job_stage_runs"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_run_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False
    )

    stage: Mapped[PipelineStage] = mapped_column(
        Enum(PipelineStage, native_enum=False, length=30), nullable=False
    )
    status: Mapped[StageStatus] = mapped_column(
        Enum(StageStatus, native_enum=False, length=20), nullable=False, default=StageStatus.pending
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    input_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    job_run: Mapped["JobRun"] = relationship("JobRun", back_populates="stage_runs")
