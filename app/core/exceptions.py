import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    message: str = "Некорректный запрос"

    def __init__(self, message: str | None = None, code: str | None = None) -> None:
        self.message = message or self.message
        self.code = code or self.code
        super().__init__(self.message)


class NotAuthenticatedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "not_authenticated"
    message = "Требуется авторизация"


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"
    message = "Недостаточно прав для выполнения действия"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "Объект не найден"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "Конфликт данных"


class TooManyRequestsError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "too_many_requests"
    message = "Слишком много запросов, попробуйте позже"


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"
    message = "Сервис временно недоступен, попробуйте позже"


def _error_response(status_code: int, code: str, message: str, details: object | None = None) -> JSONResponse:
    body: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    headers = {"WWW-Authenticate": "Bearer"} if status_code == status.HTTP_401_UNAUTHORIZED else None
    return JSONResponse(status_code=status_code, content={"error": jsonable_encoder(body)}, headers=headers)


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return _error_response(exc.status_code, exc.code, exc.message)


async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Ошибка запроса"
    return _error_response(exc.status_code, "http_error", message)


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
        for error in exc.errors()
    ]
    return _error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "validation_error", "Проверьте корректность данных", details
    )


def _is_database_connection_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in {
        "ConnectionDoesNotExistError",
        "InterfaceError",
        "OperationalError",
        "ConnectionResetError",
        "ConnectionRefusedError",
        "TimeoutError",
    }:
        return True
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "connection was closed",
            "connection refused",
            "could not connect",
            "server closed the connection",
            "connection does not exist",
        )
    )


def _exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if any(_is_database_connection_error(item) for item in _exception_chain(exc)):
        logger.error("База данных недоступна: %s %s (%s)", request.method, request.url.path, exc)
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "service_unavailable",
            "База данных недоступна. Запустите PostgreSQL: docker compose up -d db",
        )
    logger.exception("Необработанная ошибка: %s %s", request.method, request.url.path, exc_info=exc)
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Внутренняя ошибка сервера, попробуйте позже"
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
