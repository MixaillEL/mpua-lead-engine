import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class CompanyEmail(Base):
    __tablename__ = "company_emails"
    __table_args__ = (
        UniqueConstraint("company_id", "email", name="uq_company_email"),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    company: Mapped["Company"] = relationship("Company", back_populates="emails")
    source: Mapped["Source"] = relationship("Source")
