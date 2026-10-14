from enum import StrEnum


class City(StrEnum):
    YEKATERINBURG = "Екатеринбург"
    NIZHNY_TAGIL = "Нижний Тагил"
    KAMENSK_URALSKY = "Каменск-Уральский"
    PERVOURALSK = "Первоуральск"
    SEROV = "Серов"
    NOVOURALSK = "Новоуральск"
    VERKHNYAYA_PYSHMA = "Верхняя Пышма"


ALLOWED_CITIES: frozenset[str] = frozenset(city.value for city in City)


def validate_city(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized not in ALLOWED_CITIES:
        raise ValueError("Город должен быть выбран из списка доступных городов")
    return normalized
