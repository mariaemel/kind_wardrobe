from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_chats_organization_id_organizations"),
        "chats",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_chats_organization_id"), "chats", ["organization_id"], unique=False)
    op.alter_column("chats", "participant_id", existing_type=sa.Uuid(), nullable=True)
    op.drop_constraint("uq_chats_listing_participant", "chats", type_="unique")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_chats_listing_participant
        ON chats (listing_id, participant_id)
        WHERE participant_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_chats_listing_organization
        ON chats (listing_id, organization_id)
        WHERE organization_id IS NOT NULL
        """
    )

    op.add_column("transfers", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.add_column("transfers", sa.Column("address_id", sa.Uuid(), nullable=True))
    op.add_column(
        "transfers",
        sa.Column(
            "kind",
            sa.Enum("peer", "organization", name="transferkind", native_enum=False, length=32),
            server_default="peer",
            nullable=False,
        ),
    )
    op.add_column("transfers", sa.Column("organization_confirmed_by_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_transfers_organization_id_organizations"),
        "transfers",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        op.f("fk_transfers_address_id_organization_addresses"),
        "transfers",
        "organization_addresses",
        ["address_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_transfers_organization_confirmed_by_id_users"),
        "transfers",
        "users",
        ["organization_confirmed_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_transfers_organization_id"), "transfers", ["organization_id"], unique=False)
    op.create_index(op.f("ix_transfers_address_id"), "transfers", ["address_id"], unique=False)
    op.alter_column("transfers", "recipient_id", existing_type=sa.Uuid(), nullable=True)

    op.add_column("transfer_history", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.add_column("transfer_history", sa.Column("listing_image", sa.String(length=500), nullable=True))
    op.create_foreign_key(
        op.f("fk_transfer_history_organization_id_organizations"),
        "transfer_history",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_transfer_history_organization_id"), "transfer_history", ["organization_id"], unique=False)
    op.create_index(op.f("ix_transfer_history_role"), "transfer_history", ["role"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_transfer_history_role"), table_name="transfer_history")
    op.drop_index(op.f("ix_transfer_history_organization_id"), table_name="transfer_history")
    op.drop_constraint(
        op.f("fk_transfer_history_organization_id_organizations"),
        "transfer_history",
        type_="foreignkey",
    )
    op.drop_column("transfer_history", "listing_image")
    op.drop_column("transfer_history", "organization_id")

    op.drop_index(op.f("ix_transfers_address_id"), table_name="transfers")
    op.drop_index(op.f("ix_transfers_organization_id"), table_name="transfers")
    op.drop_constraint(op.f("fk_transfers_organization_confirmed_by_id_users"), "transfers", type_="foreignkey")
    op.drop_constraint(op.f("fk_transfers_address_id_organization_addresses"), "transfers", type_="foreignkey")
    op.drop_constraint(op.f("fk_transfers_organization_id_organizations"), "transfers", type_="foreignkey")
    op.drop_column("transfers", "organization_confirmed_by_id")
    op.drop_column("transfers", "kind")
    op.drop_column("transfers", "address_id")
    op.drop_column("transfers", "organization_id")
    op.alter_column("transfers", "recipient_id", existing_type=sa.Uuid(), nullable=False)

    op.execute("DROP INDEX IF EXISTS uq_chats_listing_organization")
    op.execute("DROP INDEX IF EXISTS uq_chats_listing_participant")
    op.create_unique_constraint("uq_chats_listing_participant", "chats", ["listing_id", "participant_id"])
    op.alter_column("chats", "participant_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_index(op.f("ix_chats_organization_id"), table_name="chats")
    op.drop_constraint(op.f("fk_chats_organization_id_organizations"), "chats", type_="foreignkey")
    op.drop_column("chats", "organization_id")
