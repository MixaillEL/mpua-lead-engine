import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, String, Text
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class JobStatus(str, enum.Enum):
    created = "created"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=20), nullable=False, default=JobStatus.created
    )
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    target_count: Mapped[int | None] = mapped_column(nullable=True)
    requested_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    sources: Mapped[list["Source"]] = relationship(
        "Source", back_populates="job", cascade="all, delete-orphan"
    )
    raw_records: Mapped[list["RawRecord"]] = relationship(
        "RawRecord", back_populates="job", cascade="all, delete-orphan"
    )
