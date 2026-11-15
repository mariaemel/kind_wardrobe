from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("about", sa.Text(), nullable=True))

    op.create_table(
        "organization_addresses",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("address_line", sa.String(length=300), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("working_hours", sa.String(length=300), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_organization_addresses_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_addresses")),
    )
    op.create_index(
        op.f("ix_organization_addresses_organization_id"),
        "organization_addresses",
        ["organization_id"],
        unique=False,
    )
    op.create_index(op.f("ix_organization_addresses_city"), "organization_addresses", ["city"], unique=False)

    op.create_table(
        "organization_acceptance_rules",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column(
            "conditions",
            postgresql.ARRAY(sa.String(length=64)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("additional_requirements", sa.Text(), nullable=True),
        sa.Column(
            "not_accepted",
            postgresql.ARRAY(sa.String(length=300)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_organization_acceptance_rules_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_acceptance_rules")),
        sa.UniqueConstraint("organization_id", name="uq_organization_acceptance_rules_org"),
    )
    op.create_index(
        op.f("ix_organization_acceptance_rules_organization_id"),
        "organization_acceptance_rules",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_organization_acceptance_rules_organization_id"),
        table_name="organization_acceptance_rules",
    )
    op.drop_table("organization_acceptance_rules")
    op.drop_index(op.f("ix_organization_addresses_city"), table_name="organization_addresses")
    op.drop_index(op.f("ix_organization_addresses_organization_id"), table_name="organization_addresses")
    op.drop_table("organization_addresses")
    op.drop_column("organizations", "about")
