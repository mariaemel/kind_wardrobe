import uuid
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile

from app.modules.accounts.dependencies import CurrentUser, OptionalUser, SessionDep
from app.modules.organizations import service
from app.modules.chats import service as chats_service
from app.modules.chats.schemas import (
    ChatResponse,
    OrganizationTransferCreateRequest,
    OrganizationTransfersResponse,
    SuitableListingsResponse,
)
from app.modules.organizations.schemas import (
    AcceptanceRulesUpdateRequest,
    AddressesReplaceRequest,
    AddressUpsertRequest,
    InvitationCreateRequest,
    InvitationResponse,
    InvitationsResponse,
    MapPointsResponse,
    MemberPermissionsUpdateRequest,
    MemberResponse,
    MembersResponse,
    MyOrganizationResponse,
    OrganizationContactsUpdateRequest,
    OrganizationCreateRequest,
    OrganizationDetailResponse,
    OrganizationGeneralUpdateRequest,
    OrganizationListResponse,
    OrganizationMembershipStatusResponse,
    OrganizationProfileUpdateRequest,
)

router = APIRouter(tags=["organizations"])


@router.get("/organizations", response_model=OrganizationListResponse)
async def list_organizations(
    session: SessionDep,
    q: str | None = None,
    city: Annotated[list[str] | None, Query()] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> OrganizationListResponse:
    items, total = await service.list_organizations(
        session, q=q, city=city, page=page, page_size=page_size
    )
    return OrganizationListResponse(
        items=[service.to_card(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/organizations/map-points", response_model=MapPointsResponse)
async def map_points(
    session: SessionDep,
    q: str | None = None,
    city: Annotated[list[str] | None, Query()] = None,
) -> MapPointsResponse:
    items = await service.list_map_points(session, q=q, city=city)
    return MapPointsResponse(items=items, total=len(items))


@router.get("/me/organizations", response_model=list[MyOrganizationResponse])
async def my_organizations(session: SessionDep, user: CurrentUser) -> list[MyOrganizationResponse]:
    items = await service.list_my_organizations(session, user)
    return [MyOrganizationResponse(**item) for item in items]


@router.get("/me/organization-status", response_model=OrganizationMembershipStatusResponse)
async def organization_status(
    session: SessionDep, user: CurrentUser
) -> OrganizationMembershipStatusResponse:
    return OrganizationMembershipStatusResponse(**await service.membership_status(session, user))


@router.post("/organizations", response_model=OrganizationDetailResponse, status_code=201)
async def create_organization(
    payload: OrganizationCreateRequest,
    session: SessionDep,
    user: CurrentUser,
) -> OrganizationDetailResponse:
    return OrganizationDetailResponse(**await service.create_organization(session, user, payload))


@router.get("/organizations/{organization_id}", response_model=OrganizationDetailResponse)
async def get_organization(
    organization_id: uuid.UUID,
    session: SessionDep,
    viewer: OptionalUser,
) -> OrganizationDetailResponse:
    payload = await service.get_public_organization(session, organization_id, viewer)
    return OrganizationDetailResponse(**payload)


@router.patch("/organizations/{organization_id}/profile", response_model=OrganizationDetailResponse)
async def patch_profile(
    organization_id: uuid.UUID,
    payload: OrganizationProfileUpdateRequest,
    session: SessionDep,
    user: CurrentUser,
) -> OrganizationDetailResponse:
    return OrganizationDetailResponse(
        **await service.update_profile_page(session, organization_id, user, payload)
    )


@router.patch("/organizations/{organization_id}/general", response_model=OrganizationDetailResponse)
async def patch_general(
    organization_id: uuid.UUID,
    payload: OrganizationGeneralUpdateRequest,
    session: SessionDep,
    user: CurrentUser,
) -> OrganizationDetailResponse:
    return OrganizationDetailResponse(
        **await service.update_general(session, organization_id, user, payload)
    )


@router.patch("/organizations/{organization_id}/contacts", response_model=OrganizationDetailResponse)
async def patch_contacts(
    organization_id: uuid.UUID,
    payload: OrganizationContactsUpdateRequest,
    session: SessionDep,
    user: CurrentUser,
) -> OrganizationDetailResponse:
    return OrganizationDetailResponse(
        **await service.update_contacts(session, organization_id, user, payload)
    )


@router.post("/organizations/{organization_id}/logo", response_model=OrganizationDetailResponse)
async def upload_logo(
    organization_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    file: UploadFile = File(...),
) -> OrganizationDetailResponse:
    return OrganizationDetailResponse(
        **await service.update_logo(session, organization_id, user, file)
    )


@router.put("/organizations/{organization_id}/addresses", response_model=OrganizationDetailResponse)
async def put_addresses(
    organization_id: uuid.UUID,
    payload: AddressesReplaceRequest,
    session: SessionDep,
    user: CurrentUser,
) -> OrganizationDetailResponse:
    return OrganizationDetailResponse(
        **await service.replace_addresses(session, organization_id, user, payload.addresses)
    )


@router.post(
    "/organizations/{organization_id}/addresses",
    response_model=OrganizationDetailResponse,
    status_code=201,
)
async def create_address(
    organization_id: uuid.UUID,
    payload: AddressUpsertRequest,
    session: SessionDep,
    user: CurrentUser,
) -> OrganizationDetailResponse:
    return OrganizationDetailResponse(
        **await service.create_address(session, organization_id, user, payload)
    )


@router.patch(
    "/organizations/{organization_id}/addresses/{address_id}",
    response_model=OrganizationDetailResponse,
)
async def patch_address(
    organization_id: uuid.UUID,
    address_id: uuid.UUID,
    payload: AddressUpsertRequest,
    session: SessionDep,
    user: CurrentUser,
) -> OrganizationDetailResponse:
    return OrganizationDetailResponse(
        **await service.update_address(session, organization_id, address_id, user, payload)
    )


@router.delete(
    "/organizations/{organization_id}/addresses/{address_id}",
    response_model=OrganizationDetailResponse,
)
async def delete_address(
    organization_id: uuid.UUID,
    address_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> OrganizationDetailResponse:
    return OrganizationDetailResponse(
        **await service.delete_address(session, organization_id, address_id, user)
    )


@router.put(
    "/organizations/{organization_id}/acceptance-rules",
    response_model=OrganizationDetailResponse,
)
async def put_acceptance_rules(
    organization_id: uuid.UUID,
    payload: AcceptanceRulesUpdateRequest,
    session: SessionDep,
    user: CurrentUser,
) -> OrganizationDetailResponse:
    return OrganizationDetailResponse(
        **await service.update_acceptance_rules(session, organization_id, user, payload)
    )


@router.get("/organizations/{organization_id}/members", response_model=MembersResponse)
async def get_members(
    organization_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> MembersResponse:
    return MembersResponse(items=await service.list_members(session, organization_id, user))


@router.patch(
    "/organizations/{organization_id}/members/{member_id}",
    response_model=MemberResponse,
)
async def patch_member_permissions(
    organization_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: MemberPermissionsUpdateRequest,
    session: SessionDep,
    user: CurrentUser,
) -> MemberResponse:
    return MemberResponse(
        **await service.update_member_permissions(
            session, organization_id, member_id, user, payload.permissions
        )
    )


@router.delete(
    "/organizations/{organization_id}/members/{member_id}",
    status_code=204,
)
async def delete_member(
    organization_id: uuid.UUID,
    member_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> None:
    await service.remove_member(session, organization_id, member_id, user)


@router.get("/organizations/{organization_id}/invitations", response_model=InvitationsResponse)
async def get_invitations(
    organization_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> InvitationsResponse:
    return InvitationsResponse(items=await service.list_invitations(session, organization_id, user))


@router.post(
    "/organizations/{organization_id}/invitations",
    response_model=InvitationResponse,
    status_code=201,
)
async def create_invitation(
    organization_id: uuid.UUID,
    payload: InvitationCreateRequest,
    session: SessionDep,
    user: CurrentUser,
) -> InvitationResponse:
    return InvitationResponse(
        **await service.create_invitation(session, organization_id, user, payload)
    )


@router.delete(
    "/organizations/{organization_id}/invitations/{invitation_id}",
    status_code=204,
)
async def delete_invitation(
    organization_id: uuid.UUID,
    invitation_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> None:
    await service.revoke_invitation(session, organization_id, invitation_id, user)


@router.post("/organization-invitations/{token}/accept", response_model=OrganizationDetailResponse)
async def accept_invitation(
    token: str,
    session: SessionDep,
    user: CurrentUser,
) -> OrganizationDetailResponse:
    return OrganizationDetailResponse(**await service.accept_invitation(session, token, user))


@router.get(
    "/organizations/{organization_id}/suitable-listings",
    response_model=SuitableListingsResponse,
)
async def suitable_listings(
    organization_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> SuitableListingsResponse:
    items = await chats_service.list_suitable_listings(session, user, organization_id)
    return SuitableListingsResponse(items=items, total=len(items))


@router.post(
    "/organizations/{organization_id}/transfers",
    response_model=ChatResponse,
    status_code=201,
)
async def create_organization_transfer(
    organization_id: uuid.UUID,
    payload: OrganizationTransferCreateRequest,
    session: SessionDep,
    user: CurrentUser,
) -> ChatResponse:
    from app.modules.chats.router import build_chat_response

    detail = await chats_service.create_organization_transfer(
        session,
        user,
        organization_id,
        listing_id=payload.listing_id,
        address_id=payload.address_id,
    )
    return build_chat_response(detail)


@router.get(
    "/organizations/{organization_id}/transfers",
    response_model=OrganizationTransfersResponse,
)
async def list_organization_transfers(
    organization_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> OrganizationTransfersResponse:
    items = await chats_service.list_organization_transfers(session, user, organization_id)
    return OrganizationTransfersResponse(items=items, total=len(items))
