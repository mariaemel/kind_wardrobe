from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.modules.chats.catalog import HistoryRole, MessageType, TransferStatus


class Chat(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chats"
    __table_args__ = (
        UniqueConstraint("listing_id", "participant_id", name="uq_chats_listing_participant"),
    )

    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    owner_last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    participant_last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ChatMessage.created_at",
    )
    transfer: Mapped[Transfer | None] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class ChatMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chat_messages"

    chat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    type: Mapped[MessageType] = mapped_column(
        str_enum(MessageType, length=32),
        default=MessageType.TEXT,
        server_default=MessageType.TEXT.value,
    )
    text: Mapped[str] = mapped_column(Text)

    chat: Mapped[Chat] = relationship(back_populates="messages")


class Transfer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transfers"

    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), unique=True, index=True
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[TransferStatus] = mapped_column(
        str_enum(TransferStatus, length=64),
        default=TransferStatus.CONFIRMATION_PENDING,
        server_default=TransferStatus.CONFIRMATION_PENDING.value,
        index=True,
    )
    owner_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    recipient_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    chat: Mapped[Chat] = relationship(back_populates="transfer")
    history_entries: Mapped[list[TransferHistoryEntry]] = relationship(
        back_populates="transfer",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TransferHistoryEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transfer_history"

    transfer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transfers.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    role: Mapped[HistoryRole] = mapped_column(str_enum(HistoryRole, length=32))
    listing_title: Mapped[str] = mapped_column(String(200))
    counterpart_name: Mapped[str] = mapped_column(String(100))
    transfer_type: Mapped[str] = mapped_column(String(32))
    city: Mapped[str] = mapped_column(String(100))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    transfer: Mapped[Transfer] = relationship(back_populates="history_entries")
