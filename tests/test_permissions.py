import pytest

from app.modules.organizations.permissions import (
    OrgMemberRole,
    OrgPermission,
    effective_permissions,
    validate_grantable,
)


def test_representative_has_all_permissions() -> None:
    assert effective_permissions(OrgMemberRole.REPRESENTATIVE, []) == frozenset(OrgPermission)


def test_employee_without_grants_can_only_chat() -> None:
    assert effective_permissions(OrgMemberRole.EMPLOYEE, []) == {OrgPermission.CHAT}


def test_edit_profile_implies_all_description_blocks() -> None:
    permissions = effective_permissions(OrgMemberRole.EMPLOYEE, ["edit_profile"])

    assert {
        OrgPermission.EDIT_GENERAL_INFO,
        OrgPermission.EDIT_CONTACTS,
        OrgPermission.EDIT_ADDRESSES,
        OrgPermission.EDIT_ACCEPTANCE_RULES,
    } <= permissions
    assert OrgPermission.MANAGE_VOLUNTEER_TASKS not in permissions


def test_single_block_permission_does_not_grant_others() -> None:
    permissions = effective_permissions(OrgMemberRole.EMPLOYEE, ["edit_contacts"])

    assert permissions == {OrgPermission.CHAT, OrgPermission.EDIT_CONTACTS}


def test_employee_cannot_get_member_management_from_stored_value() -> None:
    permissions = effective_permissions(OrgMemberRole.EMPLOYEE, ["manage_members", "removed_permission"])

    assert permissions == {OrgPermission.CHAT}


def test_validate_grantable_rejects_unknown_and_non_grantable() -> None:
    assert validate_grantable(["confirm_transfers"]) == {OrgPermission.CONFIRM_TRANSFERS}
    with pytest.raises(ValueError):
        validate_grantable(["manage_members"])
    with pytest.raises(ValueError):
        validate_grantable(["fly_to_the_moon"])
