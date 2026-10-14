import io
import uuid
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings
from app.core.exceptions import AppError

ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


class InvalidImageError(AppError):
    status_code = 400
    code = "invalid_image"
    message = "Недопустимый файл изображения"


def _media_root() -> Path:
    settings = get_settings()
    root = Path(settings.media_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _extension_for_upload(content_type: str, image_format: str) -> str:
    if content_type in ALLOWED_IMAGE_CONTENT_TYPES:
        return ALLOWED_IMAGE_CONTENT_TYPES[content_type]
    return {
        "JPEG": ".jpg",
        "PNG": ".png",
        "WEBP": ".webp",
    }[image_format]


async def save_user_avatar(user_id: uuid.UUID, upload: UploadFile) -> str:
    settings = get_settings()
    content_type = (upload.content_type or "").lower()
    if content_type and content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise InvalidImageError("Допустимы только изображения JPEG, PNG или WebP")

    data = await upload.read()
    if not data:
        raise InvalidImageError("Файл изображения пустой")
    if len(data) > settings.max_upload_size_bytes:
        max_mb = settings.max_upload_size_bytes // (1024 * 1024)
        raise InvalidImageError(f"Размер файла не должен превышать {max_mb} МБ")

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
            image_format = (image.format or "").upper()
    except UnidentifiedImageError as exc:
        raise InvalidImageError("Файл не является изображением") from exc

    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise InvalidImageError("Допустимы только изображения JPEG, PNG или WebP")

    relative_dir = Path("avatars") / str(user_id)
    absolute_dir = _media_root() / relative_dir
    absolute_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{_extension_for_upload(content_type, image_format)}"
    absolute_path = absolute_dir / filename
    absolute_path.write_bytes(data)

    return f"{settings.media_url.rstrip('/')}/{relative_dir.as_posix()}/{filename}"


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
