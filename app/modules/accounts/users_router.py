import uuid

from fastapi import APIRouter, Query

from app.core.exceptions import NotFoundError
from app.modules.accounts.dependencies import SessionDep
from app.modules.accounts.models import User
from app.modules.accounts.profile_service import profile_items_saved
from app.modules.accounts.schemas import PublicProfileResponse
from app.modules.listings import service as listings_service
from app.modules.listings.schemas import ListingCardResponse, ListingListResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}", response_model=PublicProfileResponse)
async def get_public_profile(user_id: uuid.UUID, session: SessionDep) -> PublicProfileResponse:
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise NotFoundError("Пользователь не найден")
    return PublicProfileResponse(
        id=user.id,
        name=user.name,
        city=user.city,
        about=user.about,
        avatar_url=user.avatar_url,
        items_saved=await profile_items_saved(session, user),
        created_at=user.created_at,
    )


@router.get("/{user_id}/listings", response_model=ListingListResponse)
async def get_user_listings(
    user_id: uuid.UUID,
    session: SessionDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ListingListResponse:
    listings, total = await listings_service.list_user_published_listings(
        session, user_id, page=page, page_size=page_size
    )
    return ListingListResponse(
        items=[ListingCardResponse(**listings_service._to_card(item)) for item in listings],
        total=total,
        page=page,
        page_size=page_size,
    )
