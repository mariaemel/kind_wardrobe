import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.listings.catalog import (
    CATEGORIES,
    DeliveryMethod,
    ListingCondition,
    ListingStatus,
    TransferType,
    validate_category_pair,
)


class CategoryNode(BaseModel):
    name: str
    subcategories: list[str]


class CategoriesResponse(BaseModel):
    categories: list[CategoryNode]


class DictionariesResponse(BaseModel):
    conditions: list[str]
    transfer_types: list[str]
    delivery_methods: list[str]
    statuses: list[str]


class ListingPhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    sort_order: int


class ListingCardResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    category: str
    subcategory: str | None
    condition: str
    transfer_type: str
    city: str
    status: str
    cover_url: str | None
    created_at: datetime


class ListingDetailResponse(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    description: str
    category: str
    subcategory: str | None
    condition: str
    transfer_type: str
    exchange_wishes: str | None
    delivery_method: str
    city: str
    status: str
    photos: list[ListingPhotoResponse]
    created_at: datetime
    updated_at: datetime


class ListingCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    category: str
    subcategory: str | None = None
    condition: ListingCondition
    transfer_type: TransferType
    exchange_wishes: str | None = Field(default=None, max_length=500)
    delivery_method: DeliveryMethod

    @field_validator("title", "description")
    @classmethod
    def strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Поле не может быть пустым")
        return normalized

    @field_validator("exchange_wishes")
    @classmethod
    def normalize_wishes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_business_rules(self) -> "ListingCreateRequest":
        category, subcategory = validate_category_pair(self.category, self.subcategory)
        self.category = category
        self.subcategory = subcategory
        if self.transfer_type is TransferType.EXCHANGE and not self.exchange_wishes:
            raise ValueError("Укажите пожелания по обмену")
        if self.transfer_type is TransferType.FREE:
            self.exchange_wishes = None
        return self


class ListingUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    category: str | None = None
    subcategory: str | None = None
    condition: ListingCondition | None = None
    transfer_type: TransferType | None = None
    exchange_wishes: str | None = Field(default=None, max_length=500)
    delivery_method: DeliveryMethod | None = None

    @field_validator("title", "description")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Поле не может быть пустым")
        return normalized

    @field_validator("exchange_wishes")
    @classmethod
    def normalize_wishes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def require_fields(self) -> "ListingUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле для обновления")
        return self


class ListingListResponse(BaseModel):
    items: list[ListingCardResponse]
    total: int
    page: int
    page_size: int


def categories_payload() -> CategoriesResponse:
    return CategoriesResponse(
        categories=[CategoryNode(name=name, subcategories=subs) for name, subs in CATEGORIES.items()]
    )


def dictionaries_payload() -> DictionariesResponse:
    return DictionariesResponse(
        conditions=[item.value for item in ListingCondition],
        transfer_types=[item.value for item in TransferType],
        delivery_methods=[item.value for item in DeliveryMethod],
        statuses=[item.value for item in ListingStatus],
    )
