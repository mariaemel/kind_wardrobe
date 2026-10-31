from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class MessageResponse(BaseModel):
    message: str = Field(examples=["Операция выполнена успешно"])
