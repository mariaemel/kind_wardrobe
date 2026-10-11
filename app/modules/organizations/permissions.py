from collections.abc import Iterable
from enum import StrEnum


class OrgMemberRole(StrEnum):
    REPRESENTATIVE = "representative"
    EMPLOYEE = "employee"


class OrgPermission(StrEnum):
    CHAT = "chat"
    EDIT_PROFILE = "edit_profile"
    EDIT_GENERAL_INFO = "edit_general_info"
    EDIT_CONTACTS = "edit_contacts"
    EDIT_ADDRESSES = "edit_addresses"
    EDIT_ACCEPTANCE_RULES = "edit_acceptance_rules"
    MANAGE_VOLUNTEER_TASKS = "manage_volunteer_tasks"
    CONFIRM_TRANSFERS = "confirm_transfers"
    MANAGE_MEMBERS = "manage_members"


PERMISSION_TITLES: dict[OrgPermission, str] = {
    OrgPermission.CHAT: "Переписка с пользователями от лица организации",
    OrgPermission.EDIT_PROFILE: "Редактирование всего описания организации",
    OrgPermission.EDIT_GENERAL_INFO: "Редактирование названия, описания и логотипа",
    OrgPermission.EDIT_CONTACTS: "Редактирование контактных данных",
    OrgPermission.EDIT_ADDRESSES: "Редактирование адресов и режима работы",
    OrgPermission.EDIT_ACCEPTANCE_RULES: "Редактирование блоков «Принимаем» и «Не принимаем»",
    OrgPermission.MANAGE_VOLUNTEER_TASKS: "Добавление потребностей в волонтёрах",
    OrgPermission.CONFIRM_TRANSFERS: "Подтверждение получения вещей",
    OrgPermission.MANAGE_MEMBERS: "Управление сотрудниками",
}

BASE_EMPLOYEE_PERMISSIONS: frozenset[OrgPermission] = frozenset({OrgPermission.CHAT})

GRANTABLE_PERMISSIONS: frozenset[OrgPermission] = frozenset(
    {
        OrgPermission.EDIT_PROFILE,
        OrgPermission.EDIT_GENERAL_INFO,
        OrgPermission.EDIT_CONTACTS,
        OrgPermission.EDIT_ADDRESSES,
        OrgPermission.EDIT_ACCEPTANCE_RULES,
        OrgPermission.MANAGE_VOLUNTEER_TASKS,
        OrgPermission.CONFIRM_TRANSFERS,
    }
)

PERMISSION_IMPLICATIONS: dict[OrgPermission, frozenset[OrgPermission]] = {
    OrgPermission.EDIT_PROFILE: frozenset(
        {
            OrgPermission.EDIT_GENERAL_INFO,
            OrgPermission.EDIT_CONTACTS,
            OrgPermission.EDIT_ADDRESSES,
            OrgPermission.EDIT_ACCEPTANCE_RULES,
        }
    ),
}


def parse_permissions(raw: Iterable[str]) -> frozenset[OrgPermission]:
    known = {permission.value for permission in OrgPermission}
    return frozenset(OrgPermission(value) for value in raw if value in known)


def effective_permissions(role: OrgMemberRole, granted: Iterable[str]) -> frozenset[OrgPermission]:
    if role == OrgMemberRole.REPRESENTATIVE:
        return frozenset(OrgPermission)

    result = set(BASE_EMPLOYEE_PERMISSIONS)
    for permission in parse_permissions(granted) & GRANTABLE_PERMISSIONS:
        result.add(permission)
        result.update(PERMISSION_IMPLICATIONS.get(permission, ()))
    return frozenset(result)


def validate_grantable(requested: Iterable[str]) -> frozenset[OrgPermission]:
    requested_set = set(requested)
    allowed = {permission.value for permission in GRANTABLE_PERMISSIONS}
    unknown = requested_set - allowed
    if unknown:
        raise ValueError(f"Недопустимые права: {', '.join(sorted(unknown))}")
    return frozenset(OrgPermission(value) for value in requested_set)
