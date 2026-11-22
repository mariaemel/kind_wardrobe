from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.modules.chats.catalog import HistoryRole, MessageType, TransferKind, TransferStatus


class Chat(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chats"

    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True
    )
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

    @property
    def is_organization_chat(self) -> bool:
        return self.organization_id is not None


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
    recipient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True
    )
    address_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organization_addresses.id", ondelete="SET NULL"), index=True, nullable=True
    )
    kind: Mapped[TransferKind] = mapped_column(
        str_enum(TransferKind, length=32),
        default=TransferKind.PEER,
        server_default=TransferKind.PEER.value,
    )
    status: Mapped[TransferStatus] = mapped_column(
        str_enum(TransferStatus, length=64),
        default=TransferStatus.CONFIRMATION_PENDING,
        server_default=TransferStatus.CONFIRMATION_PENDING.value,
        index=True,
    )
    owner_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    recipient_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    organization_confirmed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    chat: Mapped[Chat] = relationship(back_populates="transfer")
    history_entries: Mapped[list[TransferHistoryEntry]] = relationship(
        back_populates="transfer",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def is_organization_transfer(self) -> bool:
        return self.kind is TransferKind.ORGANIZATION or self.organization_id is not None


class TransferHistoryEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transfer_history"

    transfer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transfers.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    role: Mapped[HistoryRole] = mapped_column(str_enum(HistoryRole, length=32), index=True)
    listing_title: Mapped[str] = mapped_column(String(200))
    listing_image: Mapped[str | None] = mapped_column(String(500))
    counterpart_name: Mapped[str] = mapped_column(String(100))
    transfer_type: Mapped[str] = mapped_column(String(32))
    city: Mapped[str] = mapped_column(String(100))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    transfer: Mapped[Transfer] = relationship(back_populates="history_entries")
