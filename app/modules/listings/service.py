import uuid
from collections.abc import Sequence

from fastapi import UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.media import delete_media_file, delete_media_files, save_image
from app.modules.accounts.models import User
from app.modules.listings.catalog import (
    ListingCondition,
    ListingStatus,
    TransferType,
    validate_category_pair,
)
from app.modules.listings.models import Listing, ListingPhoto
from app.modules.listings.schemas import ListingCreateRequest, ListingUpdateRequest


class ListingValidationError(AppError):
    status_code = 400
    code = "listing_validation_error"
    message = "Некорректные данные объявления"


EDITABLE_STATUSES = {ListingStatus.PUBLISHED, ListingStatus.UNPUBLISHED}


def _to_card(listing: Listing) -> dict:
    cover = listing.photos[0].url if listing.photos else None
    return {
        "id": listing.id,
        "title": listing.title,
        "description": listing.description,
        "category": listing.category,
        "subcategory": listing.subcategory,
        "condition": listing.condition.value,
        "transfer_type": listing.transfer_type.value,
        "city": listing.city,
        "status": listing.status.value,
        "cover_url": cover,
        "created_at": listing.created_at,
    }


def _to_detail(listing: Listing) -> dict:
    return {
        "id": listing.id,
        "owner_id": listing.owner_id,
        "title": listing.title,
        "description": listing.description,
        "category": listing.category,
        "subcategory": listing.subcategory,
        "condition": listing.condition.value,
        "transfer_type": listing.transfer_type.value,
        "exchange_wishes": listing.exchange_wishes,
        "delivery_method": listing.delivery_method.value,
        "city": listing.city,
        "status": listing.status.value,
        "photos": listing.photos,
        "created_at": listing.created_at,
        "updated_at": listing.updated_at,
    }


async def _get_listing(session: AsyncSession, listing_id: uuid.UUID) -> Listing:
    result = await session.execute(
        select(Listing).options(selectinload(Listing.photos)).where(Listing.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    if listing is None:
        raise NotFoundError("Объявление не найдено")
    return listing


def _ensure_owner(listing: Listing, user: User) -> None:
    if listing.owner_id != user.id:
        raise PermissionDeniedError("Управлять объявлением может только владелец")


def _ensure_editable(listing: Listing) -> None:
    if listing.status not in EDITABLE_STATUSES:
        raise ConflictError("Объявление нельзя изменить в текущем статусе")


async def create_listing(
    session: AsyncSession,
    owner: User,
    payload: ListingCreateRequest,
    photos: Sequence[UploadFile],
) -> Listing:
    if not owner.city:
        raise ListingValidationError("Укажите город в профиле перед созданием объявления")
    if not photos:
        raise ListingValidationError("Добавьте от 1 до 5 фотографий")

    listing = Listing(
        owner_id=owner.id,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        subcategory=payload.subcategory,
        condition=payload.condition,
        transfer_type=payload.transfer_type,
        exchange_wishes=payload.exchange_wishes,
        delivery_method=payload.delivery_method,
        city=owner.city,
        status=ListingStatus.PUBLISHED,
    )
    session.add(listing)
    await session.flush()

    urls = []
    for index, upload in enumerate(photos):
        url = await save_image(upload, folder=f"listings/{listing.id}")
        urls.append(url)
        session.add(ListingPhoto(listing_id=listing.id, url=url, sort_order=index))

    try:
        await session.commit()
    except Exception:
        delete_media_files(urls)
        raise

    return await _get_listing(session, listing.id)


async def update_listing(
    session: AsyncSession, user: User, listing_id: uuid.UUID, payload: ListingUpdateRequest
) -> Listing:
    listing = await _get_listing(session, listing_id)
    _ensure_owner(listing, user)
    _ensure_editable(listing)

    data = payload.model_dump(exclude_unset=True)
    category = data.get("category", listing.category)
    subcategory = (
        data.get("subcategory", listing.subcategory)
        if "subcategory" in data or "category" in data
        else listing.subcategory
    )
    if "category" in data or "subcategory" in data:
        category, subcategory = validate_category_pair(category, subcategory)
        data["category"] = category
        data["subcategory"] = subcategory

    transfer_type = data.get("transfer_type", listing.transfer_type)
    if isinstance(transfer_type, str):
        transfer_type = TransferType(transfer_type)
    exchange_wishes = data.get("exchange_wishes", listing.exchange_wishes)
    if transfer_type is TransferType.EXCHANGE:
        if "exchange_wishes" in data and not exchange_wishes:
            raise ListingValidationError("Укажите пожелания по обмену")
        if "transfer_type" in data and "exchange_wishes" not in data and not listing.exchange_wishes:
            raise ListingValidationError("Укажите пожелания по обмену")
    if transfer_type is TransferType.FREE:
        data["exchange_wishes"] = None

    for field, value in data.items():
        setattr(listing, field, value)

    session.add(listing)
    await session.commit()
    return await _get_listing(session, listing.id)


async def unpublish_listing(session: AsyncSession, user: User, listing_id: uuid.UUID) -> Listing:
    listing = await _get_listing(session, listing_id)
    _ensure_owner(listing, user)
    if listing.status is not ListingStatus.PUBLISHED:
        raise ConflictError("Снять с публикации можно только опубликованное объявление")
    listing.status = ListingStatus.UNPUBLISHED
    session.add(listing)
    await session.commit()
    return await _get_listing(session, listing.id)


async def publish_listing(session: AsyncSession, user: User, listing_id: uuid.UUID) -> Listing:
    listing = await _get_listing(session, listing_id)
    _ensure_owner(listing, user)
    if listing.status is not ListingStatus.UNPUBLISHED:
        raise ConflictError("Опубликовать можно только снятое с публикации объявление")
    if not listing.photos:
        raise ListingValidationError("Для публикации нужно хотя бы одно фото")
    listing.status = ListingStatus.PUBLISHED
    session.add(listing)
    await session.commit()
    return await _get_listing(session, listing.id)


async def add_photos(
    session: AsyncSession, user: User, listing_id: uuid.UUID, photos: Sequence[UploadFile]
) -> Listing:
    listing = await _get_listing(session, listing_id)
    _ensure_owner(listing, user)
    _ensure_editable(listing)
    if not photos:
        raise ListingValidationError("Добавьте хотя бы одно фото")
    if len(listing.photos) + len(photos) > 5:
        raise ListingValidationError("Можно загрузить не более 5 фотографий")

    start = len(listing.photos)
    urls: list[str] = []
    for offset, upload in enumerate(photos):
        url = await save_image(upload, folder=f"listings/{listing.id}")
        urls.append(url)
        session.add(ListingPhoto(listing_id=listing.id, url=url, sort_order=start + offset))
    try:
        await session.commit()
    except Exception:
        delete_media_files(urls)
        raise
    return await _get_listing(session, listing.id)


async def delete_photo(
    session: AsyncSession, user: User, listing_id: uuid.UUID, photo_id: uuid.UUID
) -> Listing:
    listing = await _get_listing(session, listing_id)
    _ensure_owner(listing, user)
    _ensure_editable(listing)
    photo = next((p for p in listing.photos if p.id == photo_id), None)
    if photo is None:
        raise NotFoundError("Фото не найдено")
    if len(listing.photos) <= 1 and listing.status is ListingStatus.PUBLISHED:
        raise ConflictError("Нельзя удалить последнее фото у опубликованного объявления")

    url = photo.url
    await session.delete(photo)
    await session.commit()
    delete_media_file(url)
    return await _get_listing(session, listing.id)


def _filter_clauses(
    *,
    q: str | None,
    category: str | None,
    subcategory: str | None,
    condition: list[ListingCondition] | None,
    city: list[str] | None,
    transfer_type: list[TransferType] | None,
    status: list[ListingStatus] | None,
) -> list:
    clauses: list = []
    if q:
        pattern = f"%{q.strip()}%"
        clauses.append(or_(Listing.title.ilike(pattern), Listing.description.ilike(pattern)))
    if category:
        clauses.append(Listing.category == category)
    if subcategory:
        clauses.append(Listing.subcategory == subcategory)
    if condition:
        clauses.append(Listing.condition.in_(condition))
    if city:
        clauses.append(Listing.city.in_(city))
    if transfer_type:
        clauses.append(Listing.transfer_type.in_(transfer_type))
    if status:
        clauses.append(Listing.status.in_(status))
    return clauses


async def list_catalog(
    session: AsyncSession,
    *,
    q: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    condition: list[ListingCondition] | None = None,
    city: list[str] | None = None,
    transfer_type: list[TransferType] | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Listing], int]:
    clauses = _filter_clauses(
        q=q,
        category=category,
        subcategory=subcategory,
        condition=condition,
        city=city,
        transfer_type=transfer_type,
        status=[ListingStatus.PUBLISHED],
    )
    total = await session.scalar(select(func.count()).select_from(Listing).where(*clauses))
    result = await session.execute(
        select(Listing)
        .options(selectinload(Listing.photos))
        .where(*clauses)
        .order_by(Listing.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().unique().all()), int(total or 0)


async def list_my_listings(
    session: AsyncSession,
    owner: User,
    *,
    q: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    condition: list[ListingCondition] | None = None,
    transfer_type: list[TransferType] | None = None,
    status: list[ListingStatus] | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Listing], int]:
    clauses = [Listing.owner_id == owner.id] + _filter_clauses(
        q=q,
        category=category,
        subcategory=subcategory,
        condition=condition,
        city=None,
        transfer_type=transfer_type,
        status=status,
    )
    total = await session.scalar(select(func.count()).select_from(Listing).where(*clauses))
    result = await session.execute(
        select(Listing)
        .options(selectinload(Listing.photos))
        .where(*clauses)
        .order_by(Listing.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().unique().all()), int(total or 0)


async def get_listing_detail(
    session: AsyncSession, listing_id: uuid.UUID, viewer: User | None
) -> Listing:
    listing = await _get_listing(session, listing_id)
    if listing.status is ListingStatus.PUBLISHED:
        return listing
    if viewer is not None and viewer.id == listing.owner_id:
        return listing
    if listing.status in {ListingStatus.IN_TRANSFER, ListingStatus.TRANSFERRED} and viewer is not None:
        return listing
    raise NotFoundError("Объявление не найдено")
