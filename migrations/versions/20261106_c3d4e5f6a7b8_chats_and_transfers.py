from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chats",
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("owner_last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("participant_last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], name=op.f("fk_chats_listing_id_listings"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_chats_owner_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["participant_id"], ["users.id"], name=op.f("fk_chats_participant_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chats")),
        sa.UniqueConstraint("listing_id", "participant_id", name="uq_chats_listing_participant"),
    )
    op.create_index(op.f("ix_chats_listing_id"), "chats", ["listing_id"], unique=False)
    op.create_index(op.f("ix_chats_owner_id"), "chats", ["owner_id"], unique=False)
    op.create_index(op.f("ix_chats_participant_id"), "chats", ["participant_id"], unique=False)

    op.create_table(
        "chat_messages",
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("sender_id", sa.Uuid(), nullable=True),
        sa.Column(
            "type",
            sa.Enum(name="messagetype", native_enum=False, length=32),
            server_default="text",
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], name=op.f("fk_chat_messages_chat_id_chats"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["sender_id"], ["users.id"], name=op.f("fk_chat_messages_sender_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_messages")),
    )
    op.create_index(op.f("ix_chat_messages_chat_id"), "chat_messages", ["chat_id"], unique=False)
    op.create_index(op.f("ix_chat_messages_sender_id"), "chat_messages", ["sender_id"], unique=False)

    op.create_table(
        "transfers",
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(name="transferstatus", native_enum=False, length=64),
            server_default="confirmation_pending",
            nullable=False,
        ),
        sa.Column("owner_confirmed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("recipient_confirmed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], name=op.f("fk_transfers_chat_id_chats"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["listings.id"], name=op.f("fk_transfers_listing_id_listings"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_transfers_owner_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["recipient_id"], ["users.id"], name=op.f("fk_transfers_recipient_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transfers")),
        sa.UniqueConstraint("chat_id", name=op.f("uq_transfers_chat_id")),
    )
    op.create_index(op.f("ix_transfers_chat_id"), "transfers", ["chat_id"], unique=True)
    op.create_index(op.f("ix_transfers_listing_id"), "transfers", ["listing_id"], unique=False)
    op.create_index(op.f("ix_transfers_owner_id"), "transfers", ["owner_id"], unique=False)
    op.create_index(op.f("ix_transfers_recipient_id"), "transfers", ["recipient_id"], unique=False)
    op.create_index(op.f("ix_transfers_status"), "transfers", ["status"], unique=False)

    op.create_table(
        "transfer_history",
        sa.Column("transfer_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Enum(name="historyrole", native_enum=False, length=32), nullable=False),
        sa.Column("listing_title", sa.String(length=200), nullable=False),
        sa.Column("counterpart_name", sa.String(length=100), nullable=False),
        sa.Column("transfer_type", sa.String(length=32), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["transfer_id"], ["transfers.id"], name=op.f("fk_transfer_history_transfer_id_transfers"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_transfer_history_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["listings.id"], name=op.f("fk_transfer_history_listing_id_listings"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transfer_history")),
    )
    op.create_index(op.f("ix_transfer_history_transfer_id"), "transfer_history", ["transfer_id"], unique=False)
    op.create_index(op.f("ix_transfer_history_user_id"), "transfer_history", ["user_id"], unique=False)
    op.create_index(op.f("ix_transfer_history_listing_id"), "transfer_history", ["listing_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_transfer_history_listing_id"), table_name="transfer_history")
    op.drop_index(op.f("ix_transfer_history_user_id"), table_name="transfer_history")
    op.drop_index(op.f("ix_transfer_history_transfer_id"), table_name="transfer_history")
    op.drop_table("transfer_history")
    op.drop_index(op.f("ix_transfers_status"), table_name="transfers")
    op.drop_index(op.f("ix_transfers_recipient_id"), table_name="transfers")
    op.drop_index(op.f("ix_transfers_owner_id"), table_name="transfers")
    op.drop_index(op.f("ix_transfers_listing_id"), table_name="transfers")
    op.drop_index(op.f("ix_transfers_chat_id"), table_name="transfers")
    op.drop_table("transfers")
    op.drop_index(op.f("ix_chat_messages_sender_id"), table_name="chat_messages")
    op.drop_index(op.f("ix_chat_messages_chat_id"), table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index(op.f("ix_chats_participant_id"), table_name="chats")
    op.drop_index(op.f("ix_chats_owner_id"), table_name="chats")
    op.drop_index(op.f("ix_chats_listing_id"), table_name="chats")
    op.drop_table("chats")
