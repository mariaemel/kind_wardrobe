import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.accounts.models import User
from app.modules.organizations.models import (
    Organization,
    OrganizationAcceptanceRules,
    OrganizationAddress,
    OrganizationMember,
)
from app.modules.organizations.permissions import OrgMemberRole
from app.modules.organizations.schedule import format_working_hours, normalize_schedule


def _weekday_schedule(start: str, end: str, *, saturday: tuple[str, str] | None = None) -> dict:
    raw = {
        "monday": {"is_open": True, "from": start, "to": end},
        "tuesday": {"is_open": True, "from": start, "to": end},
        "wednesday": {"is_open": True, "from": start, "to": end},
        "thursday": {"is_open": True, "from": start, "to": end},
        "friday": {"is_open": True, "from": start, "to": end},
        "saturday": (
            {"is_open": True, "from": saturday[0], "to": saturday[1]}
            if saturday
            else {"is_open": False, "from": None, "to": None}
        ),
        "sunday": {"is_open": False, "from": None, "to": None},
    }
    return normalize_schedule(raw)

SEED_ORGS = [
    {
        "name": "Добрые вещи",
        "email": "hello@dobro-vechi.example",
        "phone": "+7 (343) 222-33-44",
        "city": "Екатеринбург",
        "description": "Помогаем семьям в трудной жизненной ситуации.",
        "about": (
            "Мы работаем в Екатеринбурге более 5 лет. Наша миссия — развивать культуру "
            "осознанного потребления и помогать тем, кто оказался в трудной жизненной ситуации. "
            "Ежемесячно мы собираем и распределяем более 2 тонн одежды и обуви. "
            "80% вещей передаются подопечным благотворительных фондов, а оставшиеся 20% "
            "реализуются через сеть благотворительных магазинов для покрытия транспортных "
            "и складских расходов."
        ),
        "representative_email": "org.dobrye@example.com",
        "representative_name": "Представитель Добрые вещи",
        "addresses": [
            {
                "title": "Центральный пункт приёма",
                "address_line": "ул. Ленина, 15",
                "city": "Екатеринбург",
                "schedule": _weekday_schedule("10:00", "20:00", saturday=("11:00", "18:00")),
                "latitude": 56.838011,
                "longitude": 60.597465,
                "sort_order": 0,
            },
            {
                "title": "Пункт на Уралмаше",
                "address_line": "ул. Победы, 42",
                "city": "Екатеринбург",
                "schedule": normalize_schedule(
                    {
                        "monday": {"is_open": False, "from": None, "to": None},
                        "tuesday": {"is_open": True, "from": "11:00", "to": "18:00"},
                        "wednesday": {"is_open": True, "from": "11:00", "to": "18:00"},
                        "thursday": {"is_open": True, "from": "11:00", "to": "18:00"},
                        "friday": {"is_open": True, "from": "11:00", "to": "18:00"},
                        "saturday": {"is_open": True, "from": "11:00", "to": "18:00"},
                        "sunday": {"is_open": False, "from": None, "to": None},
                    }
                ),
                "latitude": 56.8885,
                "longitude": 60.6132,
                "sort_order": 1,
            },
            {
                "title": "Пункт на ВИЗе",
                "address_line": "ул. Татищева, 88",
                "city": "Екатеринбург",
                "schedule": _weekday_schedule("12:00", "20:00"),
                "latitude": 56.8458,
                "longitude": 60.5591,
                "sort_order": 2,
            },
        ],
        "acceptance": {
            "categories": [
                {
                    "name": "Одежда",
                    "subcategories": [
                        "Верхняя одежда",
                        "Футболки и топы",
                        "Брюки и джинсы",
                        "Свитеры и толстовки",
                    ],
                },
                {
                    "name": "Обувь",
                    "subcategories": ["Зимняя", "Демисезонная", "Спортивная"],
                },
                {
                    "name": "Аксессуары",
                    "subcategories": [
                        "Сумки и рюкзаки",
                        "Шарфы и перчатки",
                        "Головные уборы",
                        "Ремни",
                    ],
                },
                {
                    "name": "Дом и быт",
                    "subcategories": ["Текстиль", "Посуда", "Декор", "Хранение"],
                },
                {
                    "name": "Детские вещи",
                    "subcategories": [
                        "Детская одежда",
                        "Детская обувь",
                        "Игрушки",
                        "Детский текстиль",
                    ],
                },
            ],
            "conditions": ["Новое", "Отличное", "Хорошее"],
            "additional_requirements": (
                "Вещи должны быть чистыми, сухими и пригодными для дальнейшего использования. "
                "Одежду и текстиль желательно передавать в пакетах или коробках."
            ),
            "not_accepted": [
                "Вещи с сильными загрязнениями",
                "Одежду и обувь с выраженными повреждениями",
                "Неисправную бытовую технику",
            ],
        },
    },
    {
        "name": "Вторая жизнь",
        "email": "info@vtoraya-zhizn.example",
        "phone": "+7 (343) 555-10-20",
        "city": "Екатеринбург",
        "description": "Помогаем семьям в трудной жизненной ситуации.",
        "about": (
            "Благотворительная организация «Вторая жизнь» принимает вещи и передаёт их "
            "нуждающимся жителям города. Работаем с волонтёрами и социальными службами."
        ),
        "representative_email": "org.vtoraya@example.com",
        "representative_name": "Представитель Вторая жизнь",
        "addresses": [
            {
                "title": "Основной склад",
                "address_line": "ул. Малышева, 36",
                "city": "Екатеринбург",
                "schedule": _weekday_schedule("09:00", "18:00"),
                "latitude": 56.8352,
                "longitude": 60.6145,
                "sort_order": 0,
            },
            {
                "title": "Пункт на Эльмаше",
                "address_line": "ул. Фронтовых Бригад, 25",
                "city": "Екатеринбург",
                "schedule": normalize_schedule(
                    {
                        "monday": {"is_open": False, "from": None, "to": None},
                        "tuesday": {"is_open": False, "from": None, "to": None},
                        "wednesday": {"is_open": True, "from": "11:00", "to": "19:00"},
                        "thursday": {"is_open": True, "from": "11:00", "to": "19:00"},
                        "friday": {"is_open": True, "from": "11:00", "to": "19:00"},
                        "saturday": {"is_open": True, "from": "11:00", "to": "19:00"},
                        "sunday": {"is_open": True, "from": "11:00", "to": "19:00"},
                    }
                ),
                "latitude": 56.8439,
                "longitude": 60.6501,
                "sort_order": 1,
            },
            {
                "title": "Пункт в Центре",
                "address_line": "пр. Ленина, 50",
                "city": "Екатеринбург",
                "schedule": _weekday_schedule("10:00", "18:00", saturday=("10:00", "18:00")),
                "latitude": 56.8378,
                "longitude": 60.5970,
                "sort_order": 2,
            },
        ],
        "acceptance": {
            "categories": [
                {"name": "Одежда", "subcategories": ["Верхняя одежда", "Платья и юбки"]},
                {"name": "Обувь", "subcategories": ["Зимняя", "Летняя"]},
                {"name": "Детские вещи", "subcategories": ["Детская одежда", "Игрушки"]},
                {"name": "Книги и канцелярия", "subcategories": ["Книги", "Учебники"]},
            ],
            "conditions": ["Новое", "Отличное", "Хорошее"],
            "additional_requirements": "Принимаем вещи в чистом виде, без сильного запаха.",
            "not_accepted": [
                "Испорченные продукты",
                "Лекарства с истёкшим сроком",
                "Опасные вещества",
            ],
        },
    },
]


async def _ensure_user(session, *, email: str, name: str) -> User:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        return user
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("Test1234!"),
        name=name,
        city="Екатеринбург",
        personal_data_consent_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    return user


async def seed() -> None:
    async with SessionLocal() as session:
        for payload in SEED_ORGS:
            result = await session.execute(
                select(Organization)
                .options(
                    selectinload(Organization.addresses),
                    selectinload(Organization.acceptance_rules),
                )
                .where(Organization.email == payload["email"])
            )
            org = result.scalar_one_or_none()
            if org is None:
                org = Organization(
                    id=uuid.uuid4(),
                    name=payload["name"],
                    email=payload["email"],
                    phone=payload["phone"],
                    city=payload["city"],
                    description=payload["description"],
                    about=payload["about"],
                )
                session.add(org)
                await session.flush()
            else:
                org.name = payload["name"]
                org.phone = payload["phone"]
                org.city = payload["city"]
                org.description = payload["description"]
                org.about = payload["about"]
                session.add(org)
                await session.execute(
                    delete(OrganizationAddress).where(OrganizationAddress.organization_id == org.id)
                )
                await session.execute(
                    delete(OrganizationAcceptanceRules).where(
                        OrganizationAcceptanceRules.organization_id == org.id
                    )
                )
                await session.flush()

            user = await _ensure_user(
                session,
                email=payload["representative_email"],
                name=payload["representative_name"],
            )
            membership = await session.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == org.id,
                    OrganizationMember.user_id == user.id,
                )
            )
            if membership.scalar_one_or_none() is None:
                session.add(
                    OrganizationMember(
                        organization_id=org.id,
                        user_id=user.id,
                        role=OrgMemberRole.REPRESENTATIVE,
                    )
                )

            for item in payload["addresses"]:
                schedule = item["schedule"]
                session.add(
                    OrganizationAddress(
                        organization_id=org.id,
                        title=item["title"],
                        address_line=item["address_line"],
                        city=item["city"],
                        schedule=schedule,
                        working_hours=format_working_hours(schedule),
                        latitude=item["latitude"],
                        longitude=item["longitude"],
                        sort_order=item["sort_order"],
                    )
                )

            acceptance = payload["acceptance"]
            session.add(
                OrganizationAcceptanceRules(
                    organization_id=org.id,
                    categories=acceptance["categories"],
                    conditions=acceptance["conditions"],
                    additional_requirements=acceptance["additional_requirements"],
                    not_accepted=acceptance["not_accepted"],
                )
            )

        await session.commit()
        print("Seeded organizations: Добрые вещи, Вторая жизнь")
        print("Representatives: org.dobrye@example.com / org.vtoraya@example.com")
        print("Password: Test1234!")


if __name__ == "__main__":
    asyncio.run(seed())
