import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class SourceType(str, enum.Enum):
    google_maps = "google_maps"
    google_search = "google_search"
    website = "website"
    directory = "directory"
    manual = "manual"
    openstreetmap = "openstreetmap"
    other = "other"


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        Index("ix_sources_type_external_id", "source_type", "external_id"),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, native_enum=False, length=20), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    job_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True
    )

    job: Mapped["Job"] = relationship("Job", back_populates="sources")
    raw_records: Mapped[list["RawRecord"]] = relationship(
        "RawRecord", back_populates="source", cascade="all, delete-orphan"
    )
