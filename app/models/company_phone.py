import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class CompanyPhone(Base):
    __tablename__ = "company_phones"
    __table_args__ = (
        # MySQL treats NULL as distinct in a unique index, so multiple rows
        # with phone_normalized=NULL are still allowed for the same company.
        UniqueConstraint("company_id", "phone_normalized", name="uq_company_phone_normalized"),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    phone_raw: Mapped[str] = mapped_column(String(50), nullable=False)
    phone_normalized: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    country_code: Mapped[str | None] = mapped_column(String(5), nullable=True)
    source_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    company: Mapped["Company"] = relationship("Company", back_populates="phones")
    source: Mapped["Source"] = relationship("Source")
