import uuid
from collections.abc import Awaitable, Callable

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.modules.accounts.dependencies import CurrentUser, SessionDep
from app.modules.organizations import service
from app.modules.organizations.models import OrganizationMember
from app.modules.organizations.permissions import OrgPermission


def require_org_permission(permission: OrgPermission) -> Callable[..., Awaitable[OrganizationMember]]:
    async def dependency(organization_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> OrganizationMember:
        organization = await service.get_organization(session, organization_id)
        if organization is None:
            raise NotFoundError("Организация не найдена")

        membership = await service.get_membership(session, organization_id, user.id)
        if membership is None or not organization.is_active or not membership.has_permission(permission):
            raise PermissionDeniedError
        return membership

    return dependency
