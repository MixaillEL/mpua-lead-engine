import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    street: Mapped[str | None] = mapped_column(String(500), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    raw_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )

    company: Mapped["Company"] = relationship("Company", back_populates="addresses")
    source: Mapped["Source"] = relationship("Source")
