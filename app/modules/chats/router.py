import uuid

from fastapi import APIRouter, Query, Response, status

from app.modules.accounts.dependencies import CurrentUser, SessionDep
from app.modules.chats import service
from app.modules.chats.catalog import HistoryFilter
from app.modules.chats.schemas import (
    ChatListResponse,
    ChatResponse,
    ListingBrief,
    MessageListResponse,
    MessageResponse,
    OrganizationBrief,
    SendMessageRequest,
    SuitableOrganizationsResponse,
    TransferHistoryResponse,
    TransferResponse,
    UserBrief,
)

listings_chat_router = APIRouter(prefix="/listings", tags=["chats"])
me_chats_router = APIRouter(prefix="/me", tags=["chats"])


def build_chat_response(payload: dict) -> ChatResponse:
    transfer = None
    if payload.get("transfer") is not None:
        transfer = TransferResponse(**payload["transfer"])
    return ChatResponse(
        id=payload["id"],
        listing_id=payload["listing_id"],
        owner_id=payload["owner_id"],
        participant_id=payload.get("participant_id"),
        organization_id=payload.get("organization_id"),
        listing=ListingBrief(**payload["listing"]),
        owner=UserBrief(**payload["owner"]),
        participant=UserBrief(**payload["participant"]) if payload.get("participant") else None,
        organization=(
            OrganizationBrief(**payload["organization"]) if payload.get("organization") else None
        ),
        transfer=transfer,
        can_start_transfer=payload.get("can_start_transfer", False),
        created=payload.get("created"),
        created_at=payload["created_at"],
    )


@listings_chat_router.post("/{listing_id}/chat", response_model=ChatResponse)
async def open_listing_chat(
    listing_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    response: Response,
) -> ChatResponse:
    chat, created = await service.open_chat(session, user, listing_id)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    payload = await service.build_open_chat_response(session, user, chat)
    return build_chat_response(payload)


@listings_chat_router.get(
    "/{listing_id}/suitable-organizations",
    response_model=SuitableOrganizationsResponse,
)
async def suitable_organizations(
    listing_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> SuitableOrganizationsResponse:
    items = await service.list_suitable_organizations(session, user, listing_id)
    return SuitableOrganizationsResponse(items=items, total=len(items))


@me_chats_router.get("/chats", response_model=ChatListResponse)
async def my_chats(
    session: SessionDep,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ChatListResponse:
    items, total, unread_total = await service.list_chats(
        session, user, page=page, page_size=page_size
    )
    return ChatListResponse(
        items=items,
        total=total,
        unread_total=unread_total,
        page=page,
        page_size=page_size,
    )


@me_chats_router.get("/chats/{chat_id}", response_model=ChatResponse)
async def get_chat(chat_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> ChatResponse:
    payload = await service.get_chat_detail(session, user, chat_id)
    return build_chat_response(payload)


@me_chats_router.get("/chats/{chat_id}/messages", response_model=MessageListResponse)
async def get_messages(
    chat_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> MessageListResponse:
    items, total = await service.list_messages(session, user, chat_id, page=page, page_size=page_size)
    return MessageListResponse(items=items, total=total, page=page, page_size=page_size)


@me_chats_router.post(
    "/chats/{chat_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(
    chat_id: uuid.UUID,
    payload: SendMessageRequest,
    session: SessionDep,
    user: CurrentUser,
) -> MessageResponse:
    return MessageResponse(**await service.send_message(session, user, chat_id, payload.text))


@me_chats_router.post("/chats/{chat_id}/transfer/start", response_model=TransferResponse)
async def start_transfer(
    chat_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> TransferResponse:
    return TransferResponse(**await service.start_transfer(session, user, chat_id))


@me_chats_router.post("/chats/{chat_id}/transfer/confirm", response_model=TransferResponse)
async def confirm_transfer(
    chat_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> TransferResponse:
    return TransferResponse(**await service.confirm_transfer(session, user, chat_id))


@me_chats_router.get("/chats/{chat_id}/transfer", response_model=TransferResponse)
async def get_transfer(
    chat_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> TransferResponse:
    return TransferResponse(**await service.get_transfer(session, user, chat_id))


@me_chats_router.get("/transfer-history", response_model=TransferHistoryResponse)
async def transfer_history(
    session: SessionDep,
    user: CurrentUser,
    filter: HistoryFilter = Query(HistoryFilter.ALL),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> TransferHistoryResponse:
    items, total = await service.list_transfer_history(
        session, user, history_filter=filter, page=page, page_size=page_size
    )
    return TransferHistoryResponse(items=items, total=total, page=page, page_size=page_size)
