from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.modules.listings.catalog import DeliveryMethod, ListingCondition, ListingStatus, TransferType


class Listing(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "listings"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100), index=True)
    subcategory: Mapped[str | None] = mapped_column(String(100), index=True)
    condition: Mapped[ListingCondition] = mapped_column(str_enum(ListingCondition, length=64), index=True)
    transfer_type: Mapped[TransferType] = mapped_column(str_enum(TransferType, length=32), index=True)
    exchange_wishes: Mapped[str | None] = mapped_column(String(500))
    delivery_method: Mapped[DeliveryMethod] = mapped_column(str_enum(DeliveryMethod, length=64))
    city: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[ListingStatus] = mapped_column(
        str_enum(ListingStatus, length=64),
        default=ListingStatus.PUBLISHED,
        server_default=ListingStatus.PUBLISHED.value,
        index=True,
    )

    photos: Mapped[list[ListingPhoto]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ListingPhoto.sort_order",
    )


class ListingPhoto(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "listing_photos"

    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    listing: Mapped[Listing] = relationship(back_populates="photos")
