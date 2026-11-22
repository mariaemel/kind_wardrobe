import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.modules.accounts.models import User
from app.modules.chats.catalog import (
    HISTORY_STATUS_LABELS,
    HistoryFilter,
    HistoryRole,
    MessageType,
    TransferKind,
    TransferStatus,
)
from app.modules.chats.models import Chat, ChatMessage, Transfer, TransferHistoryEntry
from app.modules.listings.catalog import ListingStatus
from app.modules.listings.models import Listing
from app.modules.organizations.matching import listing_matches_organization
from app.modules.organizations.models import Organization, OrganizationAddress, OrganizationMember
from app.modules.organizations.permissions import OrgPermission
from app.modules.organizations.schedule import format_working_hours


def _listing_image(listing: Listing) -> str | None:
    return listing.photos[0].url if listing.photos else None


def _listing_brief(listing: Listing) -> dict:
    return {
        "id": listing.id,
        "title": listing.title,
        "image": _listing_image(listing),
        "transfer_type": listing.transfer_type.value,
        "status": listing.status.value,
        "category": listing.category,
        "subcategory": listing.subcategory,
        "condition": listing.condition.value,
    }


def _user_brief(user: User) -> dict:
    return {"id": user.id, "name": user.name, "avatar_url": user.avatar_url}


def _org_brief(org: Organization) -> dict:
    return {
        "id": org.id,
        "name": org.name,
        "logo_url": org.logo_url,
        "city": org.city,
    }


def _address_brief(address: OrganizationAddress | None) -> dict | None:
    if address is None:
        return None
    hours = address.working_hours or format_working_hours(address.schedule)
    return {
        "id": address.id,
        "title": address.title,
        "address_line": address.address_line,
        "city": address.city,
        "working_hours": hours,
    }


def _transfer_payload(
    transfer: Transfer,
    *,
    viewer: User | None = None,
    listing_status: str | None = None,
    can_start: bool | None = None,
    address: OrganizationAddress | None = None,
    organization: Organization | None = None,
    can_confirm_org: bool | None = None,
) -> dict:
    current_confirmed = None
    can_confirm = None
    if viewer is not None:
        if transfer.is_organization_transfer:
            if viewer.id == transfer.owner_id:
                current_confirmed = transfer.owner_confirmed
                can_confirm = not transfer.owner_confirmed and transfer.status is not TransferStatus.COMPLETED
            elif can_confirm_org:
                current_confirmed = transfer.recipient_confirmed
                can_confirm = not transfer.recipient_confirmed and transfer.status is not TransferStatus.COMPLETED
            else:
                current_confirmed = False
                can_confirm = False
        elif viewer.id == transfer.owner_id:
            current_confirmed = transfer.owner_confirmed
            can_confirm = not transfer.owner_confirmed and transfer.status is not TransferStatus.COMPLETED
        elif transfer.recipient_id is not None and viewer.id == transfer.recipient_id:
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
        "organization_id": transfer.organization_id,
        "address_id": transfer.address_id,
        "kind": transfer.kind.value,
        "status": transfer.status.value,
        "owner_confirmed": transfer.owner_confirmed,
        "recipient_confirmed": transfer.recipient_confirmed,
        "organization_confirmed": transfer.recipient_confirmed if transfer.is_organization_transfer else None,
        "current_user_confirmed": current_confirmed,
        "can_confirm": can_confirm,
        "can_start": can_start,
        "listing_status": listing_status,
        "address": _address_brief(address),
        "organization": _org_brief(organization) if organization is not None else None,
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


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _unread_count_for(chat: Chat, viewer: User, *, is_org_member: bool = False) -> int:
    if viewer.id == chat.owner_id:
        last_read = chat.owner_last_read_at
    elif chat.participant_id is not None and viewer.id == chat.participant_id:
        last_read = chat.participant_last_read_at
    elif is_org_member:
        last_read = chat.participant_last_read_at
    else:
        return 0
    unread = 0
    for message in chat.messages:
        if message.sender_id is None or message.sender_id == viewer.id:
            continue
        if last_read is None or _as_utc(message.created_at) > _as_utc(last_read):
            unread += 1
    return unread


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


async def _get_membership(
    session: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
) -> OrganizationMember | None:
    result = await session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def _ensure_chat_access(
    session: AsyncSession, chat: Chat, user: User
) -> OrganizationMember | None:
    if user.id == chat.owner_id:
        return None
    if chat.participant_id is not None and user.id == chat.participant_id:
        return None
    if chat.organization_id is not None:
        membership = await _get_membership(session, chat.organization_id, user.id)
        if membership is not None and membership.has_permission(OrgPermission.CHAT):
            return membership
    raise PermissionDeniedError("Чат доступен только его участникам")


async def _users_map(session: AsyncSession, *user_ids: uuid.UUID | None) -> dict[uuid.UUID, User]:
    ids = [item for item in user_ids if item is not None]
    if not ids:
        return {}
    result = await session.execute(select(User).where(User.id.in_(ids)))
    return {user.id: user for user in result.scalars().all()}


async def _load_organization(session: AsyncSession, organization_id: uuid.UUID) -> Organization:
    result = await session.execute(
        select(Organization)
        .options(
            selectinload(Organization.addresses),
            selectinload(Organization.acceptance_rules),
        )
        .where(Organization.id == organization_id)
    )
    org = result.scalar_one_or_none()
    if org is None or not org.is_active:
        raise NotFoundError("Организация не найдена")
    return org


async def _load_address(
    session: AsyncSession, organization_id: uuid.UUID, address_id: uuid.UUID
) -> OrganizationAddress:
    address = await session.get(OrganizationAddress, address_id)
    if address is None or address.organization_id != organization_id:
        raise NotFoundError("Пункт приёма не найден")
    return address


async def open_chat(session: AsyncSession, viewer: User, listing_id: uuid.UUID) -> tuple[Chat, bool]:
    listing = await _load_listing(session, listing_id)
    if listing.owner_id == viewer.id:
        raise ConflictError("Нельзя создать чат по собственному объявлению")
    if listing.status in {ListingStatus.TRANSFERRED, ListingStatus.UNPUBLISHED}:
        raise ConflictError("Нельзя начать диалог по этому объявлению")
    if listing.status is ListingStatus.IN_TRANSFER:
        raise ConflictError("Объявление уже находится в процессе передачи")

    existing = await session.execute(
        select(Chat).where(
            Chat.listing_id == listing.id,
            Chat.participant_id == viewer.id,
            Chat.organization_id.is_(None),
        )
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
    membership = await _ensure_chat_access(session, chat, viewer)
    listing = await _load_listing(session, chat.listing_id)
    users = await _users_map(session, chat.owner_id, chat.participant_id)
    owner = users[chat.owner_id]
    participant = users.get(chat.participant_id) if chat.participant_id else None
    organization = None
    if chat.organization_id is not None:
        organization = await _load_organization(session, chat.organization_id)
    active_transfer = chat.transfer or await _get_transfer_for_chat(session, chat.id)
    can_start = (
        viewer.id == chat.owner_id
        and active_transfer is None
        and listing.status is ListingStatus.PUBLISHED
        and not chat.is_organization_chat
    )
    transfer = None
    if active_transfer is not None:
        address = None
        if active_transfer.address_id is not None:
            address = await session.get(OrganizationAddress, active_transfer.address_id)
        can_confirm_org = bool(
            membership is not None and membership.has_permission(OrgPermission.CONFIRM_TRANSFERS)
        )
        transfer = _transfer_payload(
            active_transfer,
            viewer=viewer,
            listing_status=listing.status.value,
            can_start=False,
            address=address,
            organization=organization,
            can_confirm_org=can_confirm_org,
        )
    await _mark_read(session, chat, viewer, is_org_member=membership is not None)
    return {
        "id": chat.id,
        "listing_id": chat.listing_id,
        "owner_id": chat.owner_id,
        "participant_id": chat.participant_id,
        "organization_id": chat.organization_id,
        "listing": _listing_brief(listing),
        "owner": _user_brief(owner),
        "participant": _user_brief(participant) if participant else None,
        "organization": _org_brief(organization) if organization else None,
        "transfer": transfer,
        "can_start_transfer": can_start,
        "created_at": chat.created_at,
    }


async def _mark_read(
    session: AsyncSession, chat: Chat, viewer: User, *, is_org_member: bool = False
) -> None:
    now = datetime.now(UTC)
    if chat.messages:
        latest_message = max(_as_utc(message.created_at) for message in chat.messages)
        stamp = max(now, latest_message)
    else:
        stamp = now
    if viewer.id == chat.owner_id:
        chat.owner_last_read_at = stamp
    elif chat.participant_id is not None and viewer.id == chat.participant_id:
        chat.participant_last_read_at = stamp
    elif is_org_member:
        chat.participant_last_read_at = stamp
    session.add(chat)
    await session.commit()


async def count_unread_messages(session: AsyncSession, viewer: User) -> int:
    memberships = await session.execute(
        select(OrganizationMember.organization_id).where(OrganizationMember.user_id == viewer.id)
    )
    org_ids = list(memberships.scalars().all())

    owner_unread = (
        select(func.count())
        .select_from(ChatMessage)
        .join(Chat, ChatMessage.chat_id == Chat.id)
        .where(
            Chat.owner_id == viewer.id,
            ChatMessage.sender_id.is_not(None),
            ChatMessage.sender_id != viewer.id,
            or_(Chat.owner_last_read_at.is_(None), ChatMessage.created_at > Chat.owner_last_read_at),
        )
    )
    participant_unread = (
        select(func.count())
        .select_from(ChatMessage)
        .join(Chat, ChatMessage.chat_id == Chat.id)
        .where(
            Chat.participant_id == viewer.id,
            ChatMessage.sender_id.is_not(None),
            ChatMessage.sender_id != viewer.id,
            or_(
                Chat.participant_last_read_at.is_(None),
                ChatMessage.created_at > Chat.participant_last_read_at,
            ),
        )
    )
    total = int(await session.scalar(owner_unread) or 0) + int(await session.scalar(participant_unread) or 0)
    if org_ids:
        org_unread = (
            select(func.count())
            .select_from(ChatMessage)
            .join(Chat, ChatMessage.chat_id == Chat.id)
            .where(
                Chat.organization_id.in_(org_ids),
                Chat.owner_id != viewer.id,
                ChatMessage.sender_id.is_not(None),
                ChatMessage.sender_id != viewer.id,
                or_(
                    Chat.participant_last_read_at.is_(None),
                    ChatMessage.created_at > Chat.participant_last_read_at,
                ),
            )
        )
        total += int(await session.scalar(org_unread) or 0)
    return total


async def list_chats(
    session: AsyncSession, viewer: User, *, page: int = 1, page_size: int = 20
) -> tuple[list[dict], int, int]:
    memberships = await session.execute(
        select(OrganizationMember.organization_id).where(OrganizationMember.user_id == viewer.id)
    )
    org_ids = list(memberships.scalars().all())
    access_clause = or_(Chat.owner_id == viewer.id, Chat.participant_id == viewer.id)
    if org_ids:
        access_clause = or_(access_clause, Chat.organization_id.in_(org_ids))

    total = await session.scalar(select(func.count()).select_from(Chat).where(access_clause))
    unread_total = await count_unread_messages(session, viewer)
    result = await session.execute(
        select(Chat)
        .options(selectinload(Chat.transfer), selectinload(Chat.messages))
        .where(access_clause)
        .order_by(Chat.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    chats = list(result.scalars().unique().all())
    if not chats:
        return [], int(total or 0), unread_total

    listing_ids = {chat.listing_id for chat in chats}
    user_ids = {chat.owner_id for chat in chats} | {
        chat.participant_id for chat in chats if chat.participant_id is not None
    }
    org_chat_ids = {chat.organization_id for chat in chats if chat.organization_id is not None}
    listings_result = await session.execute(
        select(Listing).options(selectinload(Listing.photos)).where(Listing.id.in_(listing_ids))
    )
    listings = {listing.id: listing for listing in listings_result.scalars().all()}
    users = await _users_map(session, *user_ids)
    orgs: dict[uuid.UUID, Organization] = {}
    if org_chat_ids:
        orgs_result = await session.execute(select(Organization).where(Organization.id.in_(org_chat_ids)))
        orgs = {org.id: org for org in orgs_result.scalars().all()}

    items: list[dict] = []
    for chat in chats:
        listing = listings[chat.listing_id]
        is_org_member = bool(
            chat.organization_id is not None
            and chat.organization_id in org_ids
            and viewer.id != chat.owner_id
        )
        if chat.organization_id is not None:
            org = orgs[chat.organization_id]
            other_user = None
            other_organization = _org_brief(org)
            display_name = org.name
        else:
            other = users[chat.participant_id if viewer.id == chat.owner_id else chat.owner_id]
            other_user = _user_brief(other)
            other_organization = None
            display_name = other.name
        last = chat.messages[-1] if chat.messages else None
        unread = _unread_count_for(chat, viewer, is_org_member=is_org_member)
        items.append(
            {
                "id": chat.id,
                "listing_id": chat.listing_id,
                "other_user": other_user,
                "other_organization": other_organization,
                "display_name": display_name,
                "listing": _listing_brief(listing),
                "last_message": (
                    {"text": last.text, "created_at": last.created_at, "type": last.type.value}
                    if last
                    else None
                ),
                "unread_count": unread,
                "has_unread": unread > 0,
                "transfer_status": chat.transfer.status.value if chat.transfer else None,
                "kind": chat.transfer.kind.value if chat.transfer else ("organization" if chat.organization_id else "peer"),
                "created_at": chat.created_at,
            }
        )
    return items, int(total or 0), unread_total


async def list_messages(
    session: AsyncSession, viewer: User, chat_id: uuid.UUID, *, page: int = 1, page_size: int = 50
) -> tuple[list[dict], int]:
    chat = await _load_chat(session, chat_id)
    membership = await _ensure_chat_access(session, chat, viewer)
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
    await _mark_read(session, chat, viewer, is_org_member=membership is not None)
    return messages, int(total or 0)


async def send_message(session: AsyncSession, viewer: User, chat_id: uuid.UUID, text: str) -> dict:
    chat = await _load_chat(session, chat_id)
    await _ensure_chat_access(session, chat, viewer)
    message = ChatMessage(chat_id=chat.id, sender_id=viewer.id, type=MessageType.TEXT, text=text)
    session.add(message)
    chat.updated_at = datetime.now(UTC)
    session.add(chat)
    await session.commit()
    await session.refresh(message)
    return _message_payload(message)


async def start_transfer(session: AsyncSession, viewer: User, chat_id: uuid.UUID) -> dict:
    chat = await _load_chat(session, chat_id)
    await _ensure_chat_access(session, chat, viewer)
    if chat.is_organization_chat:
        raise ConflictError("Для передачи организации подтверждение уже оформлено при создании")
    if viewer.id != chat.owner_id:
        raise PermissionDeniedError("Запустить передачу может только автор объявления")
    if chat.transfer is not None:
        raise ConflictError("Передача по этому чату уже запущена")
    if chat.participant_id is None:
        raise ConflictError("Нельзя начать передачу без получателя")

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
        kind=TransferKind.PEER,
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
    membership = await _ensure_chat_access(session, chat, viewer)
    transfer = chat.transfer or await _get_transfer_for_chat(session, chat.id)
    if transfer is None:
        raise ConflictError("Передача ещё не запущена")
    if transfer.status is TransferStatus.COMPLETED:
        raise ConflictError("Передача уже завершена")

    listing = await _load_listing(session, chat.listing_id)
    organization = None
    address = None
    if transfer.is_organization_transfer:
        if transfer.organization_id is None:
            raise ConflictError("Организация передачи не указана")
        organization = await _load_organization(session, transfer.organization_id)
        if transfer.address_id is not None:
            address = await session.get(OrganizationAddress, transfer.address_id)
        if viewer.id == transfer.owner_id:
            if transfer.owner_confirmed:
                raise ConflictError("Вы уже подтвердили передачу")
            transfer.owner_confirmed = True
            system_text = "Пользователь отметил действие «Передал организации»."
        elif membership is not None and membership.has_permission(OrgPermission.CONFIRM_TRANSFERS):
            if transfer.recipient_confirmed:
                raise ConflictError("Получение уже подтверждено организацией")
            transfer.recipient_confirmed = True
            transfer.organization_confirmed_by_id = viewer.id
            system_text = "Организация подтвердила получение вещи."
        else:
            raise PermissionDeniedError("Недостаточно прав для подтверждения получения")
    else:
        if viewer.id == transfer.owner_id:
            if transfer.owner_confirmed:
                raise ConflictError("Вы уже подтвердили передачу")
            transfer.owner_confirmed = True
            system_text = "Владелец подтвердил передачу вещи."
        elif transfer.recipient_id is not None and viewer.id == transfer.recipient_id:
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
        system_text = (
            "Передача завершена. Объявление перенесено в архив."
            if not transfer.is_organization_transfer
            else "Передача организации завершена. Объявление перенесено в архив."
        )
        await _write_history(session, transfer, listing, organization)
    elif transfer.owner_confirmed or transfer.recipient_confirmed:
        transfer.status = TransferStatus.WAITING_SECOND_CONFIRMATION
        listing.status = ListingStatus.IN_TRANSFER

    session.add(transfer)
    session.add(listing)
    session.add(ChatMessage(chat_id=chat.id, sender_id=None, type=MessageType.SYSTEM, text=system_text))
    chat.updated_at = datetime.now(UTC)
    session.add(chat)
    await session.commit()
    transfer = await _get_transfer_for_chat(session, chat.id)
    if transfer is None:
        raise NotFoundError("Передача не найдена")
    listing = await _load_listing(session, transfer.listing_id)
    can_confirm_org = bool(
        membership is not None and membership.has_permission(OrgPermission.CONFIRM_TRANSFERS)
    )
    return _transfer_payload(
        transfer,
        viewer=viewer,
        listing_status=listing.status.value,
        can_start=False,
        address=address,
        organization=organization,
        can_confirm_org=can_confirm_org,
    )


async def get_transfer(session: AsyncSession, viewer: User, chat_id: uuid.UUID) -> dict:
    chat = await _load_chat(session, chat_id)
    membership = await _ensure_chat_access(session, chat, viewer)
    transfer = chat.transfer or await _get_transfer_for_chat(session, chat.id)
    if transfer is None:
        raise NotFoundError("Передача не найдена")
    listing = await _load_listing(session, chat.listing_id)
    organization = None
    address = None
    if transfer.organization_id is not None:
        organization = await _load_organization(session, transfer.organization_id)
    if transfer.address_id is not None:
        address = await session.get(OrganizationAddress, transfer.address_id)
    can_confirm_org = bool(
        membership is not None and membership.has_permission(OrgPermission.CONFIRM_TRANSFERS)
    )
    return _transfer_payload(
        transfer,
        viewer=viewer,
        listing_status=listing.status.value,
        can_start=False,
        address=address,
        organization=organization,
        can_confirm_org=can_confirm_org,
    )


async def _write_history(
    session: AsyncSession,
    transfer: Transfer,
    listing: Listing,
    organization: Organization | None = None,
) -> None:
    users = await _users_map(session, transfer.owner_id, transfer.recipient_id)
    owner = users[transfer.owner_id]
    completed_at = transfer.completed_at or datetime.now(UTC)
    image = _listing_image(listing)
    if transfer.is_organization_transfer:
        org_name = organization.name if organization is not None else "Организация"
        session.add(
            TransferHistoryEntry(
                transfer_id=transfer.id,
                user_id=owner.id,
                listing_id=listing.id,
                organization_id=transfer.organization_id,
                role=HistoryRole.TO_ORGANIZATION,
                listing_title=listing.title,
                listing_image=image,
                counterpart_name=org_name,
                transfer_type=listing.transfer_type.value,
                city=listing.city,
                completed_at=completed_at,
            )
        )
        return

    recipient = users[transfer.recipient_id]
    session.add(
        TransferHistoryEntry(
            transfer_id=transfer.id,
            user_id=owner.id,
            listing_id=listing.id,
            role=HistoryRole.OWNER,
            listing_title=listing.title,
            listing_image=image,
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
            listing_image=image,
            counterpart_name=owner.name,
            transfer_type=listing.transfer_type.value,
            city=listing.city,
            completed_at=completed_at,
        )
    )


async def list_transfer_history(
    session: AsyncSession,
    viewer: User,
    *,
    history_filter: HistoryFilter = HistoryFilter.ALL,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    clauses = [TransferHistoryEntry.user_id == viewer.id]
    if history_filter is HistoryFilter.TRANSFERRED:
        clauses.append(TransferHistoryEntry.role == HistoryRole.OWNER)
    elif history_filter is HistoryFilter.RECEIVED:
        clauses.append(TransferHistoryEntry.role == HistoryRole.RECIPIENT)
    elif history_filter is HistoryFilter.TO_ORGANIZATIONS:
        clauses.append(TransferHistoryEntry.role == HistoryRole.TO_ORGANIZATION)

    total = await session.scalar(
        select(func.count()).select_from(TransferHistoryEntry).where(*clauses)
    )
    result = await session.execute(
        select(TransferHistoryEntry)
        .where(*clauses)
        .order_by(TransferHistoryEntry.completed_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        {
            "id": entry.id,
            "transfer_id": entry.transfer_id,
            "listing_id": entry.listing_id,
            "organization_id": entry.organization_id,
            "role": entry.role.value,
            "status_label": HISTORY_STATUS_LABELS[entry.role],
            "listing_title": entry.listing_title,
            "listing_image": entry.listing_image,
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


async def eco_tracker_counts(session: AsyncSession, user_id: uuid.UUID) -> dict[str, int]:
    received = await session.scalar(
        select(func.count())
        .select_from(TransferHistoryEntry)
        .where(
            TransferHistoryEntry.user_id == user_id,
            TransferHistoryEntry.role == HistoryRole.RECIPIENT,
        )
    )
    transferred = await session.scalar(
        select(func.count())
        .select_from(TransferHistoryEntry)
        .where(
            TransferHistoryEntry.user_id == user_id,
            TransferHistoryEntry.role.in_([HistoryRole.OWNER, HistoryRole.TO_ORGANIZATION]),
        )
    )
    received_count = int(received or 0)
    transferred_count = int(transferred or 0)
    return {
        "items_received": received_count,
        "items_transferred": transferred_count,
        "items_saved": received_count + transferred_count,
    }


async def build_open_chat_response(session: AsyncSession, viewer: User, chat: Chat) -> dict:
    return await get_chat_detail(session, viewer, chat.id)


async def list_suitable_organizations(session: AsyncSession, viewer: User, listing_id: uuid.UUID) -> list[dict]:
    listing = await _load_listing(session, listing_id)
    if listing.owner_id != viewer.id:
        raise PermissionDeniedError("Подбор организаций доступен только автору объявления")
    if listing.status is not ListingStatus.PUBLISHED:
        raise ConflictError("Передать можно только опубликованное объявление")

    from app.modules.organizations.models import OrganizationStatus

    result = await session.execute(
        select(Organization)
        .options(
            selectinload(Organization.addresses),
            selectinload(Organization.acceptance_rules),
        )
        .where(Organization.status == OrganizationStatus.ACTIVE)
        .order_by(Organization.name.asc())
    )
    items = []
    for org in result.scalars().unique().all():
        if listing_matches_organization(listing, org):
            items.append(
                {
                    **_org_brief(org),
                    "description": org.description,
                    "points_count": len(org.addresses),
                    "acceptance_tags": [
                        item.get("name") if isinstance(item, dict) else str(item)
                        for item in ((org.acceptance_rules.categories if org.acceptance_rules else None) or [])
                        if (item.get("name") if isinstance(item, dict) else item)
                    ],
                }
            )
    return items


async def list_suitable_listings(
    session: AsyncSession, viewer: User, organization_id: uuid.UUID
) -> list[dict]:
    org = await _load_organization(session, organization_id)
    result = await session.execute(
        select(Listing)
        .options(selectinload(Listing.photos))
        .where(
            Listing.owner_id == viewer.id,
            Listing.status == ListingStatus.PUBLISHED,
        )
        .order_by(Listing.created_at.desc())
    )
    return [
        _listing_brief(listing)
        for listing in result.scalars().unique().all()
        if listing_matches_organization(listing, org)
    ]


async def create_organization_transfer(
    session: AsyncSession,
    viewer: User,
    organization_id: uuid.UUID,
    listing_id: uuid.UUID,
    address_id: uuid.UUID,
) -> dict:
    org = await _load_organization(session, organization_id)
    listing = await _load_listing(session, listing_id)
    if listing.owner_id != viewer.id:
        raise PermissionDeniedError("Передать можно только своё объявление")
    if listing.status is not ListingStatus.PUBLISHED:
        raise ConflictError("Передать можно только опубликованное объявление")
    if not listing_matches_organization(listing, org):
        raise ConflictError("Объявление не подходит этой организации по категории или состоянию")
    address = await _load_address(session, org.id, address_id)

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

    existing = await session.execute(
        select(Chat).where(
            Chat.listing_id == listing.id,
            Chat.organization_id == org.id,
        )
    )
    chat = existing.scalar_one_or_none()
    created = False
    if chat is None:
        chat = Chat(
            listing_id=listing.id,
            owner_id=viewer.id,
            participant_id=None,
            organization_id=org.id,
        )
        session.add(chat)
        await session.flush()
        created = True
    else:
        chat = await _load_chat(session, chat.id)
        if chat.transfer is not None and chat.transfer.status is not TransferStatus.COMPLETED:
            raise ConflictError("Передача этой вещи организации уже оформлена")

    hours = address.working_hours or format_working_hours(address.schedule)
    transfer = Transfer(
        chat_id=chat.id,
        listing_id=listing.id,
        owner_id=viewer.id,
        recipient_id=None,
        organization_id=org.id,
        address_id=address.id,
        kind=TransferKind.ORGANIZATION,
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
            text=(
                f"Оформлена передача организации «{org.name}». "
                f"Пункт приёма: {address.address_line} · {hours}. "
                "Отметьте фактическую передачу после вручения вещи."
            ),
        )
    )
    chat.updated_at = datetime.now(UTC)
    session.add(chat)
    await session.commit()
    detail = await get_chat_detail(session, viewer, chat.id)
    detail["created"] = created
    return detail


async def list_organization_transfers(
    session: AsyncSession, viewer: User, organization_id: uuid.UUID
) -> list[dict]:
    membership = await _get_membership(session, organization_id, viewer.id)
    if membership is None:
        raise PermissionDeniedError("Недостаточно прав для просмотра передач")
    org = await _load_organization(session, organization_id)
    result = await session.execute(
        select(Transfer)
        .options(selectinload(Transfer.chat).selectinload(Chat.messages))
        .where(Transfer.organization_id == organization_id)
        .order_by(Transfer.created_at.desc())
    )
    transfers = list(result.scalars().unique().all())
    if not transfers:
        return []

    listing_ids = {item.listing_id for item in transfers}
    user_ids = {item.owner_id for item in transfers}
    address_ids = {item.address_id for item in transfers if item.address_id is not None}
    listings_result = await session.execute(
        select(Listing).options(selectinload(Listing.photos)).where(Listing.id.in_(listing_ids))
    )
    listings = {listing.id: listing for listing in listings_result.scalars().all()}
    users = await _users_map(session, *user_ids)
    addresses: dict[uuid.UUID, OrganizationAddress] = {}
    if address_ids:
        addresses_result = await session.execute(
            select(OrganizationAddress).where(OrganizationAddress.id.in_(address_ids))
        )
        addresses = {item.id: item for item in addresses_result.scalars().all()}

    can_confirm_org = membership.has_permission(OrgPermission.CONFIRM_TRANSFERS)
    items = []
    for transfer in transfers:
        listing = listings[transfer.listing_id]
        owner = users[transfer.owner_id]
        address = addresses.get(transfer.address_id) if transfer.address_id else None
        payload = _transfer_payload(
            transfer,
            viewer=viewer,
            listing_status=listing.status.value,
            address=address,
            organization=org,
            can_confirm_org=can_confirm_org,
        )
        payload["listing"] = _listing_brief(listing)
        payload["owner"] = _user_brief(owner)
        if transfer.status is TransferStatus.CONFIRMATION_PENDING and not transfer.owner_confirmed:
            payload["status_label"] = "Ожидает передачи владельцем"
        elif transfer.owner_confirmed and not transfer.recipient_confirmed:
            payload["status_label"] = "Владелец подтвердил передачу"
        elif transfer.status is TransferStatus.COMPLETED:
            payload["status_label"] = "Передача завершена"
        else:
            payload["status_label"] = transfer.status.value
        items.append(payload)
    return items
