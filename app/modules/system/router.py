import logging

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import ServiceUnavailableError
from app.modules.accounts.dependencies import SessionDep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: str
    database: str


@router.get("/health", response_model=HealthResponse)
async def health(session: SessionDep) -> HealthResponse:
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        logger.error("База данных недоступна: %s", exc)
        raise ServiceUnavailableError("База данных временно недоступна") from exc
    return HealthResponse(status="ok", database="ok")
