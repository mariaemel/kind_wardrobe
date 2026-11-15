from __future__ import annotations

DAY_ORDER = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

DAY_LABELS = {
    "monday": "Пн",
    "tuesday": "Вт",
    "wednesday": "Ср",
    "thursday": "Чт",
    "friday": "Пт",
    "saturday": "Сб",
    "sunday": "Вс",
}


def empty_schedule() -> dict[str, dict]:
    return {
        day: {"is_open": False, "from": None, "to": None}
        for day in DAY_ORDER
    }


def normalize_schedule(raw: dict | None) -> dict[str, dict]:
    schedule = empty_schedule()
    if not raw:
        return schedule
    for day in DAY_ORDER:
        value = raw.get(day) or {}
        is_open = bool(value.get("is_open"))
        start = value.get("from")
        end = value.get("to")
        if is_open:
            if not start or not end:
                raise ValueError(f"Для дня «{DAY_LABELS[day]}» укажите время начала и окончания")
            schedule[day] = {"is_open": True, "from": str(start), "to": str(end)}
        else:
            schedule[day] = {"is_open": False, "from": None, "to": None}
    return schedule


def format_working_hours(schedule: dict | None) -> str:
    normalized = normalize_schedule(schedule)
    open_days = [
        (day, normalized[day]["from"], normalized[day]["to"])
        for day in DAY_ORDER
        if normalized[day]["is_open"]
    ]
    if not open_days:
        return "По договорённости"

    groups: list[tuple[list[str], str, str]] = []
    for day, start, end in open_days:
        if groups and groups[-1][1] == start and groups[-1][2] == end:
            groups[-1][0].append(day)
        else:
            groups.append(([day], start or "", end or ""))

    parts: list[str] = []
    for days, start, end in groups:
        if len(days) == 1:
            label = DAY_LABELS[days[0]]
        else:
            label = f"{DAY_LABELS[days[0]]}-{DAY_LABELS[days[-1]]}"
        parts.append(f"{label} {start}–{end}")
    return ", ".join(parts)
