import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class CompanySource(Base):
    """Provenance link: which Source(s) confirm/contributed to a Company.

    Deleting a Source does NOT delete the Company (ON DELETE CASCADE here
    only removes the link row, matching the "no dangerous Company deletion"
    rule already used for CompanyPhone/Email/Website/Address/SocialLink).
    """

    __tablename__ = "company_sources"
    __table_args__ = (
        UniqueConstraint("company_id", "source_id", name="uq_company_source"),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    company: Mapped["Company"] = relationship("Company", back_populates="company_sources")
    source: Mapped["Source"] = relationship("Source")
