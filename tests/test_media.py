import io
from pathlib import Path

import pytest
from fastapi import UploadFile
from PIL import Image
from starlette.datastructures import Headers

from app.core.config import get_settings
from app.core.media import InvalidImageError, save_image, save_images


def _image_upload(name: str, fmt: str = "PNG", content_type: str | None = None) -> UploadFile:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 20, 30)).save(buffer, format=fmt)
    data = buffer.getvalue()
    if content_type is None:
        content_type = "image/png" if fmt == "PNG" else "image/jpeg"
    return UploadFile(
        file=io.BytesIO(data),
        filename=name,
        headers=Headers({"content-type": content_type}),
    )


async def test_save_image_stores_under_folder() -> None:
    url = await save_image(_image_upload("a.png"), folder="listings/demo")
    assert url.startswith("/media/listings/demo/")
    path = Path(get_settings().media_root) / url.removeprefix("/media/")
    assert path.is_file()


async def test_save_images_respects_max_count() -> None:
    uploads = [_image_upload(f"{index}.png") for index in range(3)]
    urls = await save_images(uploads, folder="listings/batch", max_count=3)
    assert len(urls) == 3

    with pytest.raises(InvalidImageError, match="не более 3"):
        await save_images(uploads + [_image_upload("extra.png")], folder="listings/batch", max_count=3)


async def test_save_image_rejects_webp() -> None:
    upload = _image_upload("a.webp", fmt="WEBP", content_type="image/webp")
    with pytest.raises(InvalidImageError, match="JPG или PNG"):
        await save_image(upload, folder="avatars/test")


async def test_save_images_rejects_empty_list() -> None:
    with pytest.raises(InvalidImageError, match="хотя бы одно"):
        await save_images([], folder="listings/empty")
