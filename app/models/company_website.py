import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class CompanyWebsite(Base):
    __tablename__ = "company_websites"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_alive: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )

    company: Mapped["Company"] = relationship("Company", back_populates="websites")
    source: Mapped["Source"] = relationship("Source")
