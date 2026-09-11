import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class RawRecord(Base):
    __tablename__ = "raw_records"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True
    )
    source_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=True
    )
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)

    job: Mapped["Job"] = relationship("Job", back_populates="raw_records")
    source: Mapped["Source"] = relationship("Source", back_populates="raw_records")
