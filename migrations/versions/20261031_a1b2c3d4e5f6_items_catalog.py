from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "c7ec924575ab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("subcategory", sa.String(length=100), nullable=True),
        sa.Column("condition", sa.Enum(name="itemcondition", native_enum=False, length=64), nullable=False),
        sa.Column("transfer_type", sa.Enum(name="transfertype", native_enum=False, length=32), nullable=False),
        sa.Column("exchange_wishes", sa.String(length=500), nullable=True),
        sa.Column("delivery_method", sa.Enum(name="deliverymethod", native_enum=False, length=64), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.Enum(name="itemstatus", native_enum=False, length=64),
            server_default="Опубликовано",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_items_owner_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_items")),
    )
    op.create_index(op.f("ix_items_owner_id"), "items", ["owner_id"], unique=False)
    op.create_index(op.f("ix_items_title"), "items", ["title"], unique=False)
    op.create_index(op.f("ix_items_category"), "items", ["category"], unique=False)
    op.create_index(op.f("ix_items_subcategory"), "items", ["subcategory"], unique=False)
    op.create_index(op.f("ix_items_condition"), "items", ["condition"], unique=False)
    op.create_index(op.f("ix_items_transfer_type"), "items", ["transfer_type"], unique=False)
    op.create_index(op.f("ix_items_city"), "items", ["city"], unique=False)
    op.create_index(op.f("ix_items_status"), "items", ["status"], unique=False)

    op.create_table(
        "item_photos",
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"], ["items.id"], name=op.f("fk_item_photos_item_id_items"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item_photos")),
    )
    op.create_index(op.f("ix_item_photos_item_id"), "item_photos", ["item_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_item_photos_item_id"), table_name="item_photos")
    op.drop_table("item_photos")
    op.drop_index(op.f("ix_items_status"), table_name="items")
    op.drop_index(op.f("ix_items_city"), table_name="items")
    op.drop_index(op.f("ix_items_transfer_type"), table_name="items")
    op.drop_index(op.f("ix_items_condition"), table_name="items")
    op.drop_index(op.f("ix_items_subcategory"), table_name="items")
    op.drop_index(op.f("ix_items_category"), table_name="items")
    op.drop_index(op.f("ix_items_title"), table_name="items")
    op.drop_index(op.f("ix_items_owner_id"), table_name="items")
    op.drop_table("items")
