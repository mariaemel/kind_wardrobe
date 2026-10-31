import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.modules.accounts.dependencies import CurrentUser, OptionalUser, SessionDep
from app.modules.listings import service
from app.modules.listings.catalog import DeliveryMethod, ListingCondition, ListingStatus, TransferType
from app.modules.listings.schemas import (
    CategoriesResponse,
    DictionariesResponse,
    ListingCardResponse,
    ListingCreateRequest,
    ListingDetailResponse,
    ListingListResponse,
    ListingUpdateRequest,
    categories_payload,
    dictionaries_payload,
)

router = APIRouter(prefix="/listings", tags=["listings"])


def _card(listing) -> ListingCardResponse:
    return ListingCardResponse(**service._to_card(listing))


def _detail(listing) -> ListingDetailResponse:
    return ListingDetailResponse(**service._to_detail(listing))


@router.get("/categories", response_model=CategoriesResponse)
async def get_categories() -> CategoriesResponse:
    return categories_payload()


@router.get("/dictionaries", response_model=DictionariesResponse)
async def get_dictionaries() -> DictionariesResponse:
    return dictionaries_payload()


@router.get("", response_model=ListingListResponse)
async def catalog(
    session: SessionDep,
    q: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    condition: Annotated[list[ListingCondition] | None, Query()] = None,
    city: Annotated[list[str] | None, Query()] = None,
    transfer_type: Annotated[list[TransferType] | None, Query()] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ListingListResponse:
    listings, total = await service.list_catalog(
        session,
        q=q,
        category=category,
        subcategory=subcategory,
        condition=condition,
        city=city,
        transfer_type=transfer_type,
        page=page,
        page_size=page_size,
    )
    return ListingListResponse(
        items=[_card(listing) for listing in listings],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/mine", response_model=ListingListResponse)
async def my_listings(
    session: SessionDep,
    user: CurrentUser,
    q: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    condition: Annotated[list[ListingCondition] | None, Query()] = None,
    transfer_type: Annotated[list[TransferType] | None, Query()] = None,
    status_filter: Annotated[list[ListingStatus] | None, Query(alias="status")] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ListingListResponse:
    listings, total = await service.list_my_listings(
        session,
        user,
        q=q,
        category=category,
        subcategory=subcategory,
        condition=condition,
        transfer_type=transfer_type,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return ListingListResponse(
        items=[_card(listing) for listing in listings],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{listing_id}", response_model=ListingDetailResponse)
async def get_listing(
    listing_id: uuid.UUID, session: SessionDep, viewer: OptionalUser
) -> ListingDetailResponse:
    listing = await service.get_listing_detail(session, listing_id, viewer)
    return _detail(listing)


@router.post("", response_model=ListingDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_listing(
    session: SessionDep,
    user: CurrentUser,
    title: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    condition: ListingCondition = Form(...),
    transfer_type: TransferType = Form(...),
    delivery_method: DeliveryMethod = Form(...),
    subcategory: str | None = Form(None),
    exchange_wishes: str | None = Form(None),
    photos: list[UploadFile] = File(...),
) -> ListingDetailResponse:
    try:
        payload = ListingCreateRequest(
            title=title,
            description=description,
            category=category,
            subcategory=subcategory,
            condition=condition,
            transfer_type=transfer_type,
            exchange_wishes=exchange_wishes,
            delivery_method=delivery_method,
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    listing = await service.create_listing(session, user, payload, photos)
    return _detail(listing)


@router.patch("/{listing_id}", response_model=ListingDetailResponse)
async def update_listing(
    listing_id: uuid.UUID,
    payload: ListingUpdateRequest,
    session: SessionDep,
    user: CurrentUser,
) -> ListingDetailResponse:
    listing = await service.update_listing(session, user, listing_id, payload)
    return _detail(listing)


@router.post("/{listing_id}/unpublish", response_model=ListingDetailResponse)
async def unpublish_listing(
    listing_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> ListingDetailResponse:
    return _detail(await service.unpublish_listing(session, user, listing_id))


@router.post("/{listing_id}/publish", response_model=ListingDetailResponse)
async def publish_listing(
    listing_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> ListingDetailResponse:
    return _detail(await service.publish_listing(session, user, listing_id))


@router.post("/{listing_id}/photos", response_model=ListingDetailResponse)
async def add_photos(
    listing_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    photos: list[UploadFile] = File(...),
) -> ListingDetailResponse:
    return _detail(await service.add_photos(session, user, listing_id, photos))


@router.delete("/{listing_id}/photos/{photo_id}", response_model=ListingDetailResponse)
async def delete_photo(
    listing_id: uuid.UUID,
    photo_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> ListingDetailResponse:
    return _detail(await service.delete_photo(session, user, listing_id, photo_id))
