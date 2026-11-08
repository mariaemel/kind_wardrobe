import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.modules.accounts.models import User
from app.modules.chats.catalog import HistoryRole, MessageType, TransferStatus
from app.modules.chats.models import Chat, ChatMessage, Transfer, TransferHistoryEntry
from app.modules.listings.catalog import ListingStatus
from app.modules.listings.models import Listing


def _listing_image(listing: Listing) -> str | None:
    return listing.photos[0].url if listing.photos else None


def _listing_brief(listing: Listing) -> dict:
    return {
        "id": listing.id,
        "title": listing.title,
        "image": _listing_image(listing),
        "transfer_type": listing.transfer_type.value,
        "status": listing.status.value,
    }


def _user_brief(user: User) -> dict:
    return {"id": user.id, "name": user.name, "avatar_url": user.avatar_url}


def _transfer_payload(
    transfer: Transfer,
    *,
    viewer: User | None = None,
    listing_status: str | None = None,
    can_start: bool | None = None,
) -> dict:
    current_confirmed = None
    can_confirm = None
    if viewer is not None:
        if viewer.id == transfer.owner_id:
            current_confirmed = transfer.owner_confirmed
            can_confirm = not transfer.owner_confirmed and transfer.status is not TransferStatus.COMPLETED
        elif viewer.id == transfer.recipient_id:
            current_confirmed = transfer.recipient_confirmed
            can_confirm = not transfer.recipient_confirmed and transfer.status is not TransferStatus.COMPLETED
        else:
            current_confirmed = False
            can_confirm = False
    return {
        "id": transfer.id,
        "chat_id": transfer.chat_id,
        "listing_id": transfer.listing_id,
        "owner_id": transfer.owner_id,
        "recipient_id": transfer.recipient_id,
        "status": transfer.status.value,
        "owner_confirmed": transfer.owner_confirmed,
        "recipient_confirmed": transfer.recipient_confirmed,
        "current_user_confirmed": current_confirmed,
        "can_confirm": can_confirm,
        "can_start": can_start,
        "listing_status": listing_status,
        "completed_at": transfer.completed_at,
        "created_at": transfer.created_at,
    }


def _message_payload(message: ChatMessage) -> dict:
    return {
        "id": message.id,
        "chat_id": message.chat_id,
        "sender_id": message.sender_id,
        "type": message.type.value,
        "text": message.text,
        "created_at": message.created_at,
    }


async def _load_listing(session: AsyncSession, listing_id: uuid.UUID) -> Listing:
    result = await session.execute(
        select(Listing).options(selectinload(Listing.photos)).where(Listing.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    if listing is None:
        raise NotFoundError("Объявление не найдено")
    return listing


async def _load_chat(session: AsyncSession, chat_id: uuid.UUID) -> Chat:
    result = await session.execute(
        select(Chat)
        .options(
            selectinload(Chat.transfer),
            selectinload(Chat.messages),
        )
        .where(Chat.id == chat_id)
    )
    chat = result.scalar_one_or_none()
    if chat is None:
        raise NotFoundError("Чат не найден")
    return chat


async def _get_transfer_for_chat(session: AsyncSession, chat_id: uuid.UUID) -> Transfer | None:
    result = await session.execute(select(Transfer).where(Transfer.chat_id == chat_id))
    return result.scalar_one_or_none()


def _ensure_member(chat: Chat, user: User) -> None:
    if user.id not in {chat.owner_id, chat.participant_id}:
        raise PermissionDeniedError("Чат доступен только его участникам")


async def _users_map(session: AsyncSession, *user_ids: uuid.UUID) -> dict[uuid.UUID, User]:
    result = await session.execute(select(User).where(User.id.in_(user_ids)))
    return {user.id: user for user in result.scalars().all()}


async def open_chat(session: AsyncSession, viewer: User, listing_id: uuid.UUID) -> tuple[Chat, bool]:
    listing = await _load_listing(session, listing_id)
    if listing.owner_id == viewer.id:
        raise ConflictError("Нельзя создать чат по собственному объявлению")
    if listing.status in {ListingStatus.TRANSFERRED, ListingStatus.UNPUBLISHED}:
        raise ConflictError("Нельзя начать диалог по этому объявлению")
    if listing.status is ListingStatus.IN_TRANSFER:
        raise ConflictError("Объявление уже находится в процессе передачи")

    existing = await session.execute(
        select(Chat).where(Chat.listing_id == listing.id, Chat.participant_id == viewer.id)
    )
    chat = existing.scalar_one_or_none()
    if chat is not None:
        return await _load_chat(session, chat.id), False

    chat = Chat(listing_id=listing.id, owner_id=listing.owner_id, participant_id=viewer.id)
    session.add(chat)
    await session.commit()
    return await _load_chat(session, chat.id), True


async def get_chat_detail(session: AsyncSession, viewer: User, chat_id: uuid.UUID) -> dict:
    chat = await _load_chat(session, chat_id)
    _ensure_member(chat, viewer)
    listing = await _load_listing(session, chat.listing_id)
    users = await _users_map(session, chat.owner_id, chat.participant_id)
    owner = users[chat.owner_id]
    participant = users[chat.participant_id]
    active_transfer = chat.transfer or await _get_transfer_for_chat(session, chat.id)
    can_start = (
        viewer.id == chat.owner_id
        and active_transfer is None
        and listing.status is ListingStatus.PUBLISHED
    )
    transfer = None
    if active_transfer is not None:
        transfer = _transfer_payload(
            active_transfer,
            viewer=viewer,
            listing_status=listing.status.value,
            can_start=False,
        )
    await _mark_read(session, chat, viewer)
    return {
        "id": chat.id,
        "listing_id": chat.listing_id,
        "owner_id": chat.owner_id,
        "participant_id": chat.participant_id,
        "listing": _listing_brief(listing),
        "owner": _user_brief(owner),
        "participant": _user_brief(participant),
        "transfer": transfer,
        "can_start_transfer": can_start,
        "created_at": chat.created_at,
    }


async def _mark_read(session: AsyncSession, chat: Chat, viewer: User) -> None:
    now = datetime.now(UTC)
    if viewer.id == chat.owner_id:
        chat.owner_last_read_at = now
    elif viewer.id == chat.participant_id:
        chat.participant_last_read_at = now
    session.add(chat)
    await session.commit()


async def list_chats(
    session: AsyncSession, viewer: User, *, page: int = 1, page_size: int = 20
) -> tuple[list[dict], int]:
    total = await session.scalar(
        select(func.count())
        .select_from(Chat)
        .where(or_(Chat.owner_id == viewer.id, Chat.participant_id == viewer.id))
    )
    result = await session.execute(
        select(Chat)
        .options(selectinload(Chat.transfer), selectinload(Chat.messages))
        .where(or_(Chat.owner_id == viewer.id, Chat.participant_id == viewer.id))
        .order_by(Chat.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    chats = list(result.scalars().unique().all())
    if not chats:
        return [], int(total or 0)

    listing_ids = {chat.listing_id for chat in chats}
    user_ids = {chat.owner_id for chat in chats} | {chat.participant_id for chat in chats}
    listings_result = await session.execute(
        select(Listing).options(selectinload(Listing.photos)).where(Listing.id.in_(listing_ids))
    )
    listings = {listing.id: listing for listing in listings_result.scalars().all()}
    users = await _users_map(session, *user_ids)

    items: list[dict] = []
    for chat in chats:
        listing = listings[chat.listing_id]
        other = users[chat.participant_id if viewer.id == chat.owner_id else chat.owner_id]
        last = chat.messages[-1] if chat.messages else None
        last_read = chat.owner_last_read_at if viewer.id == chat.owner_id else chat.participant_last_read_at
        unread = 0
        for message in chat.messages:
            if message.sender_id == viewer.id:
                continue
            if last_read is None or message.created_at > last_read:
                unread += 1
        items.append(
            {
                "id": chat.id,
                "listing_id": chat.listing_id,
                "other_user": _user_brief(other),
                "listing": _listing_brief(listing),
                "last_message": (
                    {"text": last.text, "created_at": last.created_at, "type": last.type.value}
                    if last
                    else None
                ),
                "unread_count": unread,
                "transfer_status": chat.transfer.status.value if chat.transfer else None,
                "created_at": chat.created_at,
            }
        )
    return items, int(total or 0)


async def list_messages(
    session: AsyncSession, viewer: User, chat_id: uuid.UUID, *, page: int = 1, page_size: int = 50
) -> tuple[list[dict], int]:
    chat = await _load_chat(session, chat_id)
    _ensure_member(chat, viewer)
    total = await session.scalar(
        select(func.count()).select_from(ChatMessage).where(ChatMessage.chat_id == chat.id)
    )
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_id == chat.id)
        .order_by(ChatMessage.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    messages = [_message_payload(message) for message in result.scalars().all()]
    await _mark_read(session, chat, viewer)
    return messages, int(total or 0)


async def send_message(session: AsyncSession, viewer: User, chat_id: uuid.UUID, text: str) -> dict:
    chat = await _load_chat(session, chat_id)
    _ensure_member(chat, viewer)
    message = ChatMessage(chat_id=chat.id, sender_id=viewer.id, type=MessageType.TEXT, text=text)
    session.add(message)
    chat.updated_at = datetime.now(UTC)
    session.add(chat)
    await session.commit()
    await session.refresh(message)
    return _message_payload(message)


async def start_transfer(session: AsyncSession, viewer: User, chat_id: uuid.UUID) -> dict:
    chat = await _load_chat(session, chat_id)
    _ensure_member(chat, viewer)
    if viewer.id != chat.owner_id:
        raise PermissionDeniedError("Запустить передачу может только автор объявления")
    if chat.transfer is not None:
        raise ConflictError("Передача по этому чату уже запущена")

    listing = await _load_listing(session, chat.listing_id)
    if listing.status is not ListingStatus.PUBLISHED:
        raise ConflictError("Передачу можно начать только для опубликованного объявления")

    active = await session.scalar(
        select(func.count())
        .select_from(Transfer)
        .where(
            Transfer.listing_id == listing.id,
            Transfer.status != TransferStatus.COMPLETED,
        )
    )
    if active:
        raise ConflictError("По этому объявлению уже есть активная передача")

    transfer = Transfer(
        chat_id=chat.id,
        listing_id=listing.id,
        owner_id=chat.owner_id,
        recipient_id=chat.participant_id,
        status=TransferStatus.CONFIRMATION_PENDING,
    )
    listing.status = ListingStatus.IN_TRANSFER
    session.add(transfer)
    session.add(listing)
    session.add(
        ChatMessage(
            chat_id=chat.id,
            sender_id=None,
            type=MessageType.SYSTEM,
            text="Владелец начал передачу вещи. Подтвердите фактическую передачу, когда она состоится.",
        )
    )
    chat.updated_at = datetime.now(UTC)
    session.add(chat)
    await session.commit()
    transfer = await _get_transfer_for_chat(session, chat.id)
    if transfer is None:
        raise ConflictError("Не удалось создать передачу")
    return _transfer_payload(
        transfer,
        viewer=viewer,
        listing_status=ListingStatus.IN_TRANSFER.value,
        can_start=False,
    )


async def confirm_transfer(session: AsyncSession, viewer: User, chat_id: uuid.UUID) -> dict:
    chat = await _load_chat(session, chat_id)
    _ensure_member(chat, viewer)
    transfer = chat.transfer or await _get_transfer_for_chat(session, chat.id)
    if transfer is None:
        raise ConflictError("Передача ещё не запущена")
    if transfer.status is TransferStatus.COMPLETED:
        raise ConflictError("Передача уже завершена")

    listing = await _load_listing(session, chat.listing_id)
    if viewer.id == transfer.owner_id:
        if transfer.owner_confirmed:
            raise ConflictError("Вы уже подтвердили передачу")
        transfer.owner_confirmed = True
        system_text = "Владелец подтвердил передачу вещи."
    elif viewer.id == transfer.recipient_id:
        if transfer.recipient_confirmed:
            raise ConflictError("Вы уже подтвердили получение")
        transfer.recipient_confirmed = True
        system_text = "Получатель подтвердил получение вещи."
    else:
        raise PermissionDeniedError("Подтверждать передачу могут только её стороны")

    if transfer.owner_confirmed and transfer.recipient_confirmed:
        transfer.status = TransferStatus.COMPLETED
        transfer.completed_at = datetime.now(UTC)
        listing.status = ListingStatus.TRANSFERRED
        system_text = "Передача завершена. Объявление перенесено в архив."
        await _write_history(session, transfer, listing)
    elif transfer.owner_confirmed or transfer.recipient_confirmed:
        transfer.status = TransferStatus.WAITING_SECOND_CONFIRMATION
        listing.status = ListingStatus.IN_TRANSFER

    session.add(transfer)
    session.add(listing)
    session.add(
        ChatMessage(chat_id=chat.id, sender_id=None, type=MessageType.SYSTEM, text=system_text)
    )
    chat.updated_at = datetime.now(UTC)
    session.add(chat)
    await session.commit()
    transfer = await _get_transfer_for_chat(session, chat.id)
    if transfer is None:
        raise NotFoundError("Передача не найдена")
    listing = await _load_listing(session, transfer.listing_id)
    return _transfer_payload(
        transfer,
        viewer=viewer,
        listing_status=listing.status.value,
        can_start=False,
    )


async def get_transfer(session: AsyncSession, viewer: User, chat_id: uuid.UUID) -> dict:
    chat = await _load_chat(session, chat_id)
    _ensure_member(chat, viewer)
    transfer = chat.transfer or await _get_transfer_for_chat(session, chat.id)
    if transfer is None:
        raise NotFoundError("Передача не найдена")
    listing = await _load_listing(session, chat.listing_id)
    return _transfer_payload(
        transfer,
        viewer=viewer,
        listing_status=listing.status.value,
        can_start=False,
    )


async def _write_history(session: AsyncSession, transfer: Transfer, listing: Listing) -> None:
    users = await _users_map(session, transfer.owner_id, transfer.recipient_id)
    owner = users[transfer.owner_id]
    recipient = users[transfer.recipient_id]
    completed_at = transfer.completed_at or datetime.now(UTC)
    session.add(
        TransferHistoryEntry(
            transfer_id=transfer.id,
            user_id=owner.id,
            listing_id=listing.id,
            role=HistoryRole.OWNER,
            listing_title=listing.title,
            counterpart_name=recipient.name,
            transfer_type=listing.transfer_type.value,
            city=listing.city,
            completed_at=completed_at,
        )
    )
    session.add(
        TransferHistoryEntry(
            transfer_id=transfer.id,
            user_id=recipient.id,
            listing_id=listing.id,
            role=HistoryRole.RECIPIENT,
            listing_title=listing.title,
            counterpart_name=owner.name,
            transfer_type=listing.transfer_type.value,
            city=listing.city,
            completed_at=completed_at,
        )
    )


async def list_transfer_history(
    session: AsyncSession, viewer: User, *, page: int = 1, page_size: int = 20
) -> tuple[list[dict], int]:
    total = await session.scalar(
        select(func.count()).select_from(TransferHistoryEntry).where(TransferHistoryEntry.user_id == viewer.id)
    )
    result = await session.execute(
        select(TransferHistoryEntry)
        .where(TransferHistoryEntry.user_id == viewer.id)
        .order_by(TransferHistoryEntry.completed_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        {
            "id": entry.id,
            "transfer_id": entry.transfer_id,
            "listing_id": entry.listing_id,
            "role": entry.role.value,
            "listing_title": entry.listing_title,
            "counterpart_name": entry.counterpart_name,
            "transfer_type": entry.transfer_type,
            "city": entry.city,
            "completed_at": entry.completed_at,
        }
        for entry in result.scalars().all()
    ]
    return items, int(total or 0)


async def count_items_saved(session: AsyncSession, user_id: uuid.UUID) -> int:
    total = await session.scalar(
        select(func.count()).select_from(TransferHistoryEntry).where(TransferHistoryEntry.user_id == user_id)
    )
    return int(total or 0)


async def build_open_chat_response(session: AsyncSession, viewer: User, chat: Chat) -> dict:
    detail = await get_chat_detail(session, viewer, chat.id)
    return detail
