import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        Index("ix_companies_normalized_name_city", "normalized_name", "normalized_city"),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_city: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviews_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    phones: Mapped[list["CompanyPhone"]] = relationship(
        "CompanyPhone", back_populates="company", cascade="all, delete-orphan"
    )
    emails: Mapped[list["CompanyEmail"]] = relationship(
        "CompanyEmail", back_populates="company", cascade="all, delete-orphan"
    )
    websites: Mapped[list["CompanyWebsite"]] = relationship(
        "CompanyWebsite", back_populates="company", cascade="all, delete-orphan"
    )
    addresses: Mapped[list["Address"]] = relationship(
        "Address", back_populates="company", cascade="all, delete-orphan"
    )
    social_links: Mapped[list["SocialLink"]] = relationship(
        "SocialLink", back_populates="company", cascade="all, delete-orphan"
    )
    company_sources: Mapped[list["CompanySource"]] = relationship(
        "CompanySource", back_populates="company", cascade="all, delete-orphan"
    )
