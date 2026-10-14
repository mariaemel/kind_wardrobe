from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.media import delete_media_file, save_user_avatar
from app.modules.accounts.models import User
from app.modules.accounts.schemas import ProfileUpdateRequest


async def update_profile(session: AsyncSession, user: User, payload: ProfileUpdateRequest) -> User:
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(user, field, value)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def update_avatar(session: AsyncSession, user: User, upload: UploadFile) -> User:
    previous_url = user.avatar_url
    user.avatar_url = await save_user_avatar(user.id, upload)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    delete_media_file(previous_url)
    return user


async def delete_avatar(session: AsyncSession, user: User) -> User:
    previous_url = user.avatar_url
    user.avatar_url = None
    session.add(user)
    await session.commit()
    await session.refresh(user)
    delete_media_file(previous_url)
    return user


def profile_items_saved(_user: User) -> int:
    return 0
