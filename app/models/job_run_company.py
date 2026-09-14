import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class JobRunCompanyResolution(str, enum.Enum):
    new = "new"
    matched = "matched"


class JobRunCompany(Base):
    """Explicit scope record: which Companies a given JobRun actually
    produced (created or matched). REVIEW decisions are never linked here
    since they don't persist a Company. This is the authoritative source
    for "what should MLE-009 export for this JobRun" — reconstructing it
    after the fact from Source/Job would be unreliable once a Company has
    been touched by multiple JobRuns.
    """

    __tablename__ = "job_run_companies"
    __table_args__ = (
        UniqueConstraint("job_run_id", "company_id", name="uq_job_run_company"),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_run_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )

    resolution: Mapped[JobRunCompanyResolution] = mapped_column(
        Enum(JobRunCompanyResolution, native_enum=False, length=20), nullable=False
    )
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    job_run: Mapped["JobRun"] = relationship("JobRun", back_populates="job_run_companies")
    company: Mapped["Company"] = relationship("Company")
