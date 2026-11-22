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


async def profile_items_saved(session: AsyncSession, user: User) -> int:
    from app.modules.chats.service import count_items_saved

    return await count_items_saved(session, user.id)


async def profile_eco_tracker(session: AsyncSession, user: User) -> dict[str, int]:
    from app.modules.chats.service import eco_tracker_counts

    return await eco_tracker_counts(session, user.id)
