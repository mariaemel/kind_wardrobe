from collections.abc import Sequence

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table("items", "listings")
    op.execute('ALTER INDEX IF EXISTS "ix_items_owner_id" RENAME TO "ix_listings_owner_id"')
    op.execute('ALTER INDEX IF EXISTS "ix_items_title" RENAME TO "ix_listings_title"')
    op.execute('ALTER INDEX IF EXISTS "ix_items_category" RENAME TO "ix_listings_category"')
    op.execute('ALTER INDEX IF EXISTS "ix_items_subcategory" RENAME TO "ix_listings_subcategory"')
    op.execute('ALTER INDEX IF EXISTS "ix_items_condition" RENAME TO "ix_listings_condition"')
    op.execute('ALTER INDEX IF EXISTS "ix_items_transfer_type" RENAME TO "ix_listings_transfer_type"')
    op.execute('ALTER INDEX IF EXISTS "ix_items_city" RENAME TO "ix_listings_city"')
    op.execute('ALTER INDEX IF EXISTS "ix_items_status" RENAME TO "ix_listings_status"')
    op.execute('ALTER TABLE listings RENAME CONSTRAINT "pk_items" TO "pk_listings"')
    op.execute(
        'ALTER TABLE listings RENAME CONSTRAINT "fk_items_owner_id_users" TO "fk_listings_owner_id_users"'
    )

    op.rename_table("item_photos", "listing_photos")
    op.execute('ALTER TABLE listing_photos RENAME COLUMN item_id TO listing_id')
    op.execute('ALTER INDEX IF EXISTS "ix_item_photos_item_id" RENAME TO "ix_listing_photos_listing_id"')
    op.execute('ALTER TABLE listing_photos RENAME CONSTRAINT "pk_item_photos" TO "pk_listing_photos"')
    op.execute(
        'ALTER TABLE listing_photos RENAME CONSTRAINT "fk_item_photos_item_id_items" '
        'TO "fk_listing_photos_listing_id_listings"'
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE listing_photos RENAME CONSTRAINT "fk_listing_photos_listing_id_listings" '
        'TO "fk_item_photos_item_id_items"'
    )
    op.execute('ALTER TABLE listing_photos RENAME CONSTRAINT "pk_listing_photos" TO "pk_item_photos"')
    op.execute('ALTER INDEX IF EXISTS "ix_listing_photos_listing_id" RENAME TO "ix_item_photos_item_id"')
    op.execute('ALTER TABLE listing_photos RENAME COLUMN listing_id TO item_id')
    op.rename_table("listing_photos", "item_photos")

    op.execute(
        'ALTER TABLE listings RENAME CONSTRAINT "fk_listings_owner_id_users" TO "fk_items_owner_id_users"'
    )
    op.execute('ALTER TABLE listings RENAME CONSTRAINT "pk_listings" TO "pk_items"')
    op.execute('ALTER INDEX IF EXISTS "ix_listings_status" RENAME TO "ix_items_status"')
    op.execute('ALTER INDEX IF EXISTS "ix_listings_city" RENAME TO "ix_items_city"')
    op.execute('ALTER INDEX IF EXISTS "ix_listings_transfer_type" RENAME TO "ix_items_transfer_type"')
    op.execute('ALTER INDEX IF EXISTS "ix_listings_condition" RENAME TO "ix_items_condition"')
    op.execute('ALTER INDEX IF EXISTS "ix_listings_subcategory" RENAME TO "ix_items_subcategory"')
    op.execute('ALTER INDEX IF EXISTS "ix_listings_category" RENAME TO "ix_items_category"')
    op.execute('ALTER INDEX IF EXISTS "ix_listings_title" RENAME TO "ix_items_title"')
    op.execute('ALTER INDEX IF EXISTS "ix_listings_owner_id" RENAME TO "ix_items_owner_id"')
    op.rename_table("listings", "items")
