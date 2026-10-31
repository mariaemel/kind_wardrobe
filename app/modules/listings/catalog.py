from enum import StrEnum


class ListingCondition(StrEnum):
    NEW = "Новое"
    EXCELLENT = "Отличное"
    GOOD = "Хорошее"
    NEEDS_REPAIR = "Требует ремонта"


class TransferType(StrEnum):
    FREE = "Бесплатно"
    EXCHANGE = "Обмен"


class DeliveryMethod(StrEnum):
    MEETING = "Встреча"
    PICKUP = "Самовывоз"
    BY_AGREEMENT = "По договоренности"


class ListingStatus(StrEnum):
    PUBLISHED = "Опубликовано"
    IN_TRANSFER = "В процессе передачи"
    TRANSFERRED = "Передано"
    UNPUBLISHED = "Снято с публикации"


CATEGORIES: dict[str, list[str]] = {
    "Одежда": [
        "Верхняя одежда",
        "Футболки и топы",
        "Рубашки и блузки",
        "Свитеры и толстовки",
        "Брюки и джинсы",
        "Платья и юбки",
        "Спортивная одежда",
        "Домашняя одежда",
    ],
    "Обувь": [
        "Демисезонная",
        "Спортивная",
        "Зимняя",
        "Летняя",
    ],
    "Аксессуары": [
        "Сумки и рюкзаки",
        "Головные уборы",
        "Шарфы и перчатки",
        "Ремни",
    ],
    "Дом и быт": [
        "Посуда",
        "Текстиль",
        "Декор",
        "Хранение",
        "Мелкая бытовая техника",
    ],
    "Детские вещи": [
        "Детская одежда",
        "Детская обувь",
        "Одежда для новорожденных",
        "Игрушки",
        "Детские книги",
        "Товары для ухода за ребенком",
        "Детский текстиль",
    ],
    "Электроника": [
        "Телефоны и аксессуары",
        "Компьютеры и аксессуары",
        "Бытовая электроника",
    ],
    "Книги и канцелярия": [
        "Книги",
        "Учебники",
        "Канцтовары",
    ],
    "Хобби и спорт": [
        "Спортивный инвентарь",
        "Творчество",
        "Настольные игры",
        "Музыкальные товары",
    ],
    "Другое": [],
}


def validate_category_pair(category: str, subcategory: str | None) -> tuple[str, str | None]:
    category = category.strip()
    if category not in CATEGORIES:
        raise ValueError("Некорректная категория")

    subs = CATEGORIES[category]
    if not subs:
        if subcategory:
            raise ValueError("Для категории «Другое» подкатегория не указывается")
        return category, None

    if not subcategory or not subcategory.strip():
        raise ValueError("Укажите подкатегорию")
    subcategory = subcategory.strip()
    if subcategory not in subs:
        raise ValueError("Некорректная подкатегория для выбранной категории")
    return category, subcategory
