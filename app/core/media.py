import io
import uuid
from collections.abc import Sequence
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings
from app.core.exceptions import AppError

ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG"}
FORMAT_EXTENSIONS = {
    "JPEG": ".jpg",
    "PNG": ".png",
}


class InvalidImageError(AppError):
    status_code = 400
    code = "invalid_image"
    message = "Недопустимый файл изображения"


def _media_root() -> Path:
    settings = get_settings()
    root = Path(settings.media_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


async def _read_and_validate_image(upload: UploadFile) -> tuple[bytes, str]:
    settings = get_settings()
    content_type = (upload.content_type or "").lower()
    if content_type and content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise InvalidImageError("Допустимы только изображения JPG или PNG")

    data = await upload.read()
    if not data:
        raise InvalidImageError("Файл изображения пустой")
    if len(data) > settings.max_upload_size_bytes:
        max_mb = settings.max_upload_size_bytes // (1024 * 1024)
        raise InvalidImageError(f"Размер файла не должен превышать {max_mb} МБ")

    try:
        with Image.open(io.BytesIO(data)) as image:
            image_format = (image.format or "").upper()
            image.load()
    except UnidentifiedImageError as exc:
        raise InvalidImageError("Файл не является изображением") from exc

    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise InvalidImageError("Допустимы только изображения JPG или PNG")

    extension = ALLOWED_IMAGE_CONTENT_TYPES.get(content_type) or FORMAT_EXTENSIONS[image_format]
    return data, extension


def _store_bytes(data: bytes, *, folder: str, extension: str) -> str:
    settings = get_settings()
    relative_dir = Path(folder)
    absolute_dir = _media_root() / relative_dir
    absolute_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{extension}"
    (absolute_dir / filename).write_bytes(data)
    return f"{settings.media_url.rstrip('/')}/{relative_dir.as_posix()}/{filename}"


async def save_image(upload: UploadFile, *, folder: str) -> str:
    data, extension = await _read_and_validate_image(upload)
    return _store_bytes(data, folder=folder, extension=extension)


async def save_images(uploads: Sequence[UploadFile], *, folder: str, max_count: int | None = None) -> list[str]:
    settings = get_settings()
    limit = max_count if max_count is not None else settings.max_images_per_item
    files = list(uploads)
    if not files:
        raise InvalidImageError("Добавьте хотя бы одно изображение")
    if len(files) > limit:
        raise InvalidImageError(f"Можно загрузить не более {limit} фотографий")

    urls: list[str] = []
    for upload in files:
        urls.append(await save_image(upload, folder=folder))
    return urls


async def save_user_avatar(user_id: uuid.UUID, upload: UploadFile) -> str:
    return await save_image(upload, folder=f"avatars/{user_id}")


def delete_media_file(public_url: str | None) -> None:
    if not public_url:
        return
    settings = get_settings()
    prefix = settings.media_url.rstrip("/") + "/"
    if not public_url.startswith(prefix):
        return
    relative = public_url[len(prefix) :]
    path = _media_root() / relative
    if path.is_file():
        path.unlink()


def delete_media_files(public_urls: Sequence[str | None]) -> None:
    for url in public_urls:
        delete_media_file(url)
