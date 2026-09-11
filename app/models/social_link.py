import enum
import hashlib
import uuid

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
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


def url_fingerprint(url: str) -> str:
    """Fixed-length sha256 hex digest used for the dedup unique index,
    since `url` (String(1000), utf8mb4) is too wide for a MySQL/InnoDB
    unique key by itself.
    """
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


class SocialLink(Base):
    __tablename__ = "social_links"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "platform", "url_fingerprint", name="uq_company_social_platform_url"
        ),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[SocialPlatform] = mapped_column(
        Enum(SocialPlatform, native_enum=False, length=20), nullable=False
    )
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    url_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    source_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )

    company: Mapped["Company"] = relationship("Company", back_populates="social_links")
    source: Mapped["Source"] = relationship("Source")
