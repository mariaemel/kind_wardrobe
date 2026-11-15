import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.modules.organizations.schedule import DAY_ORDER, normalize_schedule


class AcceptanceCategory(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    subcategories: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Название категории не может быть пустым")
        return normalized

    @field_validator("subcategories")
    @classmethod
    def strip_subs(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]


class AcceptanceRulesResponse(BaseModel):
    categories: list[AcceptanceCategory]
    conditions: list[str]
    additional_requirements: str | None
    not_accepted: list[str]


class DaySchedule(BaseModel):
    is_open: bool = False
    from_time: str | None = Field(default=None, alias="from")
    to_time: str | None = Field(default=None, alias="to")

    model_config = ConfigDict(populate_by_name=True)


class ScheduleModel(BaseModel):
    monday: DaySchedule = Field(default_factory=DaySchedule)
    tuesday: DaySchedule = Field(default_factory=DaySchedule)
    wednesday: DaySchedule = Field(default_factory=DaySchedule)
    thursday: DaySchedule = Field(default_factory=DaySchedule)
    friday: DaySchedule = Field(default_factory=DaySchedule)
    saturday: DaySchedule = Field(default_factory=DaySchedule)
    sunday: DaySchedule = Field(default_factory=DaySchedule)

    def to_storage(self) -> dict:
        raw = {}
        for day in DAY_ORDER:
            value = getattr(self, day)
            raw[day] = {
                "is_open": value.is_open,
                "from": value.from_time,
                "to": value.to_time,
            }
        return normalize_schedule(raw)

    @model_validator(mode="after")
    def validate_open_days(self) -> "ScheduleModel":
        self.to_storage()
        return self


class AddressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    address_line: str
    city: str
    working_hours: str
    schedule: dict
    latitude: float | None
    longitude: float | None
    sort_order: int


class OrganizationCardResponse(BaseModel):
    id: uuid.UUID
    name: str
    city: str | None
    cities: list[str]
    logo_url: str | None
    description: str | None
    acceptance_tags: list[str]
    points_count: int


class OrganizationListResponse(BaseModel):
    items: list[OrganizationCardResponse]
    total: int
    page: int
    page_size: int


class OrganizationDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    city: str | None
    cities: list[str]
    logo_url: str | None
    description: str | None
    about: str | None
    email: str
    phone: str | None
    website: str | None
    social_links: list[dict | str] = Field(default_factory=list)
    acceptance_tags: list[str]
    points_count: int
    acceptance_rules: AcceptanceRulesResponse
    addresses: list[AddressResponse]
    viewer_permissions: list[str] = Field(default_factory=list)
    viewer_role: str | None = None
    created_at: datetime
    updated_at: datetime


class MapPointResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str
    organization_logo_url: str | None
    title: str
    address_line: str
    city: str
    working_hours: str
    latitude: float | None
    longitude: float | None


class MapPointsResponse(BaseModel):
    items: list[MapPointResponse]
    total: int


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Название не может быть пустым")
        return normalized


class OrganizationGeneralUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    about: str | None = Field(default=None, max_length=10000)
    logo_url: str | None = Field(default=None, max_length=500)
    city: str | None = None
    website: str | None = Field(default=None, max_length=500)
    social_links: list[dict | str] | None = None

    @field_validator("name", "description", "about", "logo_url", "city", "website")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def require_fields(self) -> "OrganizationGeneralUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле")
        return self


class OrganizationContactsUpdateRequest(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    website: str | None = Field(default=None, max_length=500)

    @field_validator("phone", "website")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def require_fields(self) -> "OrganizationContactsUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле")
        return self


class OrganizationProfileUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    about: str | None = Field(default=None, max_length=10000)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    website: str | None = Field(default=None, max_length=500)
    social_links: list[dict | str] | None = None

    @field_validator("name", "description", "about", "phone", "website")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def require_fields(self) -> "OrganizationProfileUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле")
        return self


class AddressUpsertRequest(BaseModel):
    id: uuid.UUID | None = None
    title: str = Field(default="", max_length=200)
    address_line: str = Field(min_length=1, max_length=300)
    city: str = Field(min_length=1, max_length=100)
    working_hours: str | None = Field(default=None, max_length=300)
    schedule: ScheduleModel | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    sort_order: int = Field(default=0, ge=0)

    @field_validator("title", "address_line", "city", "working_hours")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @model_validator(mode="after")
    def require_address(self) -> "AddressUpsertRequest":
        if not self.address_line:
            raise ValueError("Укажите адрес")
        if not self.city:
            raise ValueError("Укажите город")
        return self


class AddressesReplaceRequest(BaseModel):
    addresses: list[AddressUpsertRequest] = Field(default_factory=list)


class AcceptanceRulesUpdateRequest(BaseModel):
    categories: list[AcceptanceCategory] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    additional_requirements: str | None = Field(default=None, max_length=5000)
    not_accepted: list[str] = Field(default_factory=list)

    @field_validator("conditions", "not_accepted")
    @classmethod
    def strip_lists(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]

    @field_validator("additional_requirements")
    @classmethod
    def strip_requirements(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class MyOrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    city: str | None
    logo_url: str | None
    role: str
    permissions: list[str]
    action: str = "manage"


class OrganizationMembershipStatusResponse(BaseModel):
    has_organization: bool
    action: str
    organization: MyOrganizationResponse | None = None


class MemberResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    email: str
    role: str
    permissions: list[str]
    permission_labels: list[str]


class MembersResponse(BaseModel):
    items: list[MemberResponse]


class InvitationCreateRequest(BaseModel):
    email: EmailStr
    permissions: list[str] = Field(default_factory=list)


class InvitationResponse(BaseModel):
    id: uuid.UUID
    email: str
    permissions: list[str]
    permission_labels: list[str]
    status: str
    token: str
    created_at: datetime


class InvitationsResponse(BaseModel):
    items: list[InvitationResponse]


class MemberPermissionsUpdateRequest(BaseModel):
    permissions: list[str] = Field(default_factory=list)
