import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


def _normalize_required_text(value: str, *, empty_message: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(empty_message)
    return normalized


class UserRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    personal_data_consent: bool

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _normalize_required_text(value, empty_message="Имя не может быть пустым")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if value.strip() != value:
            raise ValueError("Пароль не должен начинаться или заканчиваться пробелом")
        if value.isspace() or not value:
            raise ValueError("Пароль не может быть пустым")
        return value

    @field_validator("personal_data_consent")
    @classmethod
    def require_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Необходимо согласие на обработку персональных данных")
        return value


class OrganizationRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    personal_data_consent: bool

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _normalize_required_text(value, empty_message="Название не может быть пустым")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if value.strip() != value:
            raise ValueError("Пароль не должен начинаться или заканчиваться пробелом")
        if value.isspace() or not value:
            raise ValueError("Пароль не может быть пустым")
        return value

    @field_validator("personal_data_consent")
    @classmethod
    def require_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Необходимо согласие на обработку персональных данных")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    city: str | None
    about: str | None
    avatar_url: str | None
    items_saved: int = 0
    system_role: str | None = None
    created_at: datetime


class UserResponse(ProfileResponse):
    pass


class ProfileUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    city: str | None = None
    about: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_required_text(value, empty_message="Имя не может быть пустым")

    @field_validator("city")
    @classmethod
    def normalize_city(cls, value: str | None) -> str | None:
        from app.modules.accounts.cities import validate_city

        return validate_city(value)

    @field_validator("about")
    @classmethod
    def normalize_about(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "ProfileUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле для обновления")
        return self


class CitiesResponse(BaseModel):
    cities: list[str]


class OrganizationBriefResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str


class AuthResponse(BaseModel):
    user: ProfileResponse
    tokens: TokenResponse


class OrganizationAuthResponse(BaseModel):
    user: ProfileResponse
    organization: OrganizationBriefResponse
    tokens: TokenResponse
