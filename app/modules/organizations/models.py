from __future__ import annotations

import uuid
from enum import StrEnum

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.modules.accounts.models import User
from app.modules.organizations.permissions import (
    OrgMemberRole,
    OrgPermission,
    effective_permissions,
)
from app.modules.organizations.schedule import empty_schedule


class OrganizationStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    about: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    phone: Mapped[str | None] = mapped_column(String(32))
    website: Mapped[str | None] = mapped_column(String(500))
    social_links: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    city: Mapped[str | None] = mapped_column(String(100), index=True)

    status: Mapped[OrganizationStatus] = mapped_column(
        str_enum(OrganizationStatus),
        default=OrganizationStatus.ACTIVE,
        server_default=OrganizationStatus.ACTIVE.value,
    )

    members: Mapped[list[OrganizationMember]] = relationship(
        back_populates="organization", cascade="all, delete-orphan", passive_deletes=True
    )
    addresses: Mapped[list[OrganizationAddress]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="OrganizationAddress.sort_order",
    )
    acceptance_rules: Mapped[OrganizationAcceptanceRules | None] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    invitations: Mapped[list[OrganizationInvitation]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def is_active(self) -> bool:
        return self.status == OrganizationStatus.ACTIVE


class OrganizationMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_organization_members_org_user"),
        UniqueConstraint("user_id", name="uq_organization_members_user"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[OrgMemberRole] = mapped_column(str_enum(OrgMemberRole))
    permissions: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, server_default=text("'{}'::varchar[]")
    )

    organization: Mapped[Organization] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")

    @property
    def effective_permissions(self) -> frozenset[OrgPermission]:
        return effective_permissions(self.role, self.permissions)

    def has_permission(self, permission: OrgPermission) -> bool:
        return permission in self.effective_permissions


class OrganizationAddress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_addresses"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="", server_default="")
    address_line: Mapped[str] = mapped_column(String(300))
    city: Mapped[str] = mapped_column(String(100), index=True)
    working_hours: Mapped[str] = mapped_column(String(300))
    schedule: Mapped[dict] = mapped_column(
        JSONB, default=empty_schedule, server_default=text("'{}'::jsonb")
    )
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    organization: Mapped[Organization] = relationship(back_populates="addresses")


class OrganizationAcceptanceRules(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_acceptance_rules"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_organization_acceptance_rules_org"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    categories: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    conditions: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, server_default=text("'{}'::varchar[]")
    )
    additional_requirements: Mapped[str | None] = mapped_column(Text)
    not_accepted: Mapped[list[str]] = mapped_column(
        ARRAY(String(300)), default=list, server_default=text("'{}'::varchar[]")
    )

    organization: Mapped[Organization] = relationship(back_populates="acceptance_rules")


class OrganizationInvitation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_invitations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    invited_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    permissions: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, server_default=text("'{}'::varchar[]")
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[InvitationStatus] = mapped_column(
        str_enum(InvitationStatus, length=32),
        default=InvitationStatus.PENDING,
        server_default=InvitationStatus.PENDING.value,
        index=True,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization: Mapped[Organization] = relationship(back_populates="invitations")
