from app.modules.listings.models import Listing
from app.modules.organizations.models import Organization, OrganizationAcceptanceRules


def _presence_cities(org: Organization) -> set[str]:
    cities = {address.city for address in org.addresses if address.city}
    if org.city:
        cities.add(org.city)
    return cities


def listing_matches_acceptance(listing: Listing, rules: OrganizationAcceptanceRules | None) -> bool:
    if rules is None:
        return False

    categories = rules.categories or []
    if not categories:
        return False

    matched_category = False
    for item in categories:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            subs = [str(sub).strip() for sub in (item.get("subcategories") or []) if str(sub).strip()]
        else:
            name = str(item).strip()
            subs = []
        if not name or name != listing.category:
            continue
        if not listing.subcategory or not subs or listing.subcategory in subs:
            matched_category = True
            break
    if not matched_category:
        return False

    conditions = list(rules.conditions or [])
    if conditions:
        condition_value = (
            listing.condition.value if hasattr(listing.condition, "value") else str(listing.condition)
        )
        if condition_value not in conditions:
            return False
    return True


def listing_matches_organization(listing: Listing, org: Organization) -> bool:
    if not org.is_active:
        return False
    cities = _presence_cities(org)
    if cities and listing.city not in cities:
        return False
    return listing_matches_acceptance(listing, org.acceptance_rules)
