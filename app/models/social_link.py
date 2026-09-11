import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class SocialPlatform(str, enum.Enum):
    facebook = "facebook"
    instagram = "instagram"
    telegram = "telegram"
    linkedin = "linkedin"
    youtube = "youtube"
    tiktok = "tiktok"
    other = "other"


class SocialLink(Base):
    __tablename__ = "social_links"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[SocialPlatform] = mapped_column(
        Enum(SocialPlatform, native_enum=False, length=20), nullable=False
    )
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )

    company: Mapped["Company"] = relationship("Company", back_populates="social_links")
    source: Mapped["Source"] = relationship("Source")
