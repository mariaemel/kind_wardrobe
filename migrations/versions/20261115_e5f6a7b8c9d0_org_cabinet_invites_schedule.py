from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "social_links",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )

    op.add_column(
        "organization_addresses",
        sa.Column(
            "schedule",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column("organization_addresses", "latitude", existing_type=sa.Float(), nullable=True)
    op.alter_column("organization_addresses", "longitude", existing_type=sa.Float(), nullable=True)

    op.create_unique_constraint("uq_organization_members_user", "organization_members", ["user_id"])

    op.create_table(
        "organization_invitations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("invited_by_id", sa.Uuid(), nullable=False),
        sa.Column(
            "permissions",
            postgresql.ARRAY(sa.String(length=64)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "accepted",
                "revoked",
                name="invitationstatus",
                native_enum=False,
                length=32,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_organization_invitations_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_id"],
            ["users.id"],
            name=op.f("fk_organization_invitations_invited_by_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_invitations")),
        sa.UniqueConstraint("token", name=op.f("uq_organization_invitations_token")),
    )
    op.create_index(
        op.f("ix_organization_invitations_organization_id"),
        "organization_invitations",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_invitations_email"),
        "organization_invitations",
        ["email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_invitations_invited_by_id"),
        "organization_invitations",
        ["invited_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_invitations_token"),
        "organization_invitations",
        ["token"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_invitations_status"),
        "organization_invitations",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_organization_invitations_status"), table_name="organization_invitations")
    op.drop_index(op.f("ix_organization_invitations_token"), table_name="organization_invitations")
    op.drop_index(op.f("ix_organization_invitations_invited_by_id"), table_name="organization_invitations")
    op.drop_index(op.f("ix_organization_invitations_email"), table_name="organization_invitations")
    op.drop_index(op.f("ix_organization_invitations_organization_id"), table_name="organization_invitations")
    op.drop_table("organization_invitations")
    op.drop_constraint("uq_organization_members_user", "organization_members", type_="unique")
    op.alter_column("organization_addresses", "longitude", existing_type=sa.Float(), nullable=False)
    op.alter_column("organization_addresses", "latitude", existing_type=sa.Float(), nullable=False)
    op.drop_column("organization_addresses", "schedule")
    op.drop_column("organizations", "social_links")
