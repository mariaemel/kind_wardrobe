import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class UserBrief(BaseModel):
    id: uuid.UUID
    name: str
    avatar_url: str | None = None


class ListingBrief(BaseModel):
    id: uuid.UUID
    title: str
    image: str | None = None
    transfer_type: str
    status: str


class TransferResponse(BaseModel):
    id: uuid.UUID
    chat_id: uuid.UUID
    listing_id: uuid.UUID
    owner_id: uuid.UUID
    recipient_id: uuid.UUID
    status: str
    owner_confirmed: bool
    recipient_confirmed: bool
    current_user_confirmed: bool | None = None
    can_confirm: bool | None = None
    can_start: bool | None = None
    listing_status: str | None = None
    completed_at: datetime | None = None
    created_at: datetime


class ChatResponse(BaseModel):
    id: uuid.UUID
    listing_id: uuid.UUID
    owner_id: uuid.UUID
    participant_id: uuid.UUID
    listing: ListingBrief
    owner: UserBrief
    participant: UserBrief
    transfer: TransferResponse | None
    can_start_transfer: bool = False
    created_at: datetime


class ChatListItem(BaseModel):
    id: uuid.UUID
    listing_id: uuid.UUID
    other_user: UserBrief
    listing: ListingBrief
    last_message: dict | None
    unread_count: int
    transfer_status: str | None = None
    created_at: datetime


class ChatListResponse(BaseModel):
    items: list[ChatListItem]
    total: int
    page: int
    page_size: int


class MessageResponse(BaseModel):
    id: uuid.UUID
    chat_id: uuid.UUID | None = None
    sender_id: uuid.UUID | None
    type: str
    text: str
    created_at: datetime


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    total: int
    page: int
    page_size: int


class SendMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Сообщение не может быть пустым")
        return normalized


class TransferHistoryItem(BaseModel):
    id: uuid.UUID
    transfer_id: uuid.UUID
    listing_id: uuid.UUID
    role: str
    listing_title: str
    counterpart_name: str
    transfer_type: str
    city: str
    completed_at: datetime


class TransferHistoryResponse(BaseModel):
    items: list[TransferHistoryItem]
    total: int
    page: int
    page_size: int
