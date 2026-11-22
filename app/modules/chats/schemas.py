import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class UserBrief(BaseModel):
    id: uuid.UUID
    name: str
    avatar_url: str | None = None


class OrganizationBrief(BaseModel):
    id: uuid.UUID
    name: str
    logo_url: str | None = None
    city: str | None = None
    description: str | None = None
    points_count: int | None = None
    acceptance_tags: list[str] = Field(default_factory=list)


class ListingBrief(BaseModel):
    id: uuid.UUID
    title: str
    image: str | None = None
    transfer_type: str
    status: str
    category: str | None = None
    subcategory: str | None = None
    condition: str | None = None


class AddressBrief(BaseModel):
    id: uuid.UUID
    title: str
    address_line: str
    city: str
    working_hours: str


class TransferResponse(BaseModel):
    id: uuid.UUID
    chat_id: uuid.UUID
    listing_id: uuid.UUID
    owner_id: uuid.UUID
    recipient_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    address_id: uuid.UUID | None = None
    kind: str = "peer"
    status: str
    owner_confirmed: bool
    recipient_confirmed: bool
    organization_confirmed: bool | None = None
    current_user_confirmed: bool | None = None
    can_confirm: bool | None = None
    can_start: bool | None = None
    listing_status: str | None = None
    address: AddressBrief | None = None
    organization: OrganizationBrief | None = None
    status_label: str | None = None
    listing: ListingBrief | None = None
    owner: UserBrief | None = None
    completed_at: datetime | None = None
    created_at: datetime


class ChatResponse(BaseModel):
    id: uuid.UUID
    listing_id: uuid.UUID
    owner_id: uuid.UUID
    participant_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    listing: ListingBrief
    owner: UserBrief
    participant: UserBrief | None = None
    organization: OrganizationBrief | None = None
    transfer: TransferResponse | None
    can_start_transfer: bool = False
    created: bool | None = None
    created_at: datetime


class ChatListItem(BaseModel):
    id: uuid.UUID
    listing_id: uuid.UUID
    other_user: UserBrief | None = None
    other_organization: OrganizationBrief | None = None
    display_name: str
    listing: ListingBrief
    last_message: dict | None
    unread_count: int
    has_unread: bool
    transfer_status: str | None = None
    kind: str = "peer"
    created_at: datetime


class ChatListResponse(BaseModel):
    items: list[ChatListItem]
    total: int
    unread_total: int
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
    organization_id: uuid.UUID | None = None
    role: str
    status_label: str
    listing_title: str
    listing_image: str | None = None
    counterpart_name: str
    transfer_type: str
    city: str
    completed_at: datetime


class TransferHistoryResponse(BaseModel):
    items: list[TransferHistoryItem]
    total: int
    page: int
    page_size: int


class SuitableOrganizationsResponse(BaseModel):
    items: list[OrganizationBrief]
    total: int


class SuitableListingsResponse(BaseModel):
    items: list[ListingBrief]
    total: int


class OrganizationTransferCreateRequest(BaseModel):
    listing_id: uuid.UUID
    address_id: uuid.UUID


class OrganizationTransfersResponse(BaseModel):
    items: list[TransferResponse]
    total: int
