from fastapi import APIRouter, File, UploadFile, status

from app.modules.accounts import profile_service
from app.modules.accounts.cities import City
from app.modules.accounts.dependencies import CurrentUser, SessionDep
from app.modules.accounts.models import User
from app.modules.accounts.schemas import CitiesResponse, ProfileResponse, ProfileUpdateRequest

router = APIRouter(tags=["profile"])


def _to_profile(user: User) -> ProfileResponse:
    return ProfileResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        city=user.city,
        about=user.about,
        avatar_url=user.avatar_url,
        items_saved=profile_service.profile_items_saved(user),
        created_at=user.created_at,
    )


@router.get("/cities", response_model=CitiesResponse)
async def list_cities() -> CitiesResponse:
    return CitiesResponse(cities=[city.value for city in City])


@router.get("/profile/me", response_model=ProfileResponse)
async def get_my_profile(user: CurrentUser) -> ProfileResponse:
    return _to_profile(user)


@router.patch("/profile/me", response_model=ProfileResponse)
async def update_my_profile(
    payload: ProfileUpdateRequest, user: CurrentUser, session: SessionDep
) -> ProfileResponse:
    updated = await profile_service.update_profile(session, user, payload)
    return _to_profile(updated)


@router.post("/profile/me/avatar", response_model=ProfileResponse)
async def upload_my_avatar(
    user: CurrentUser,
    session: SessionDep,
    file: UploadFile = File(...),
) -> ProfileResponse:
    updated = await profile_service.update_avatar(session, user, file)
    return _to_profile(updated)


@router.delete("/profile/me/avatar", response_model=ProfileResponse, status_code=status.HTTP_200_OK)
async def delete_my_avatar(user: CurrentUser, session: SessionDep) -> ProfileResponse:
    updated = await profile_service.delete_avatar(session, user)
    return _to_profile(updated)
