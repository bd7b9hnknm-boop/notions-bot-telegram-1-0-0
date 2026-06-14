"""
Логика тарифов. Здесь описано, что доступно на каждом плане,
и проверки лимитов. Оплата сюда же подключается в будущем
(пока тариф меняется вручную/админом — задел под платежи).
"""
from __future__ import annotations

from dataclasses import dataclass

from config import settings

# Названия тарифов (одно место истины)
FREE = "free"
PRO = "pro"
PREMIUM = "premium"

VALID_TARIFFS = {FREE, PRO, PREMIUM}


@dataclass(frozen=True)
class TariffInfo:
    code: str
    title: str
    price: str
    notes_limit: int | None        # None = безлимит
    daily_advice: bool             # умные советы каждый день
    analytics: bool                # аналитика продуктивности
    export: bool                   # экспорт в Notion/Calendar
    priority_ai: bool              # приоритет/более точная модель
    family: bool                   # семейный доступ


TARIFFS: dict[str, TariffInfo] = {
    FREE: TariffInfo(
        code=FREE,
        title="FREE",
        price="бесплатно",
        notes_limit=settings.free_notes_limit,
        daily_advice=False,
        analytics=False,
        export=False,
        priority_ai=False,
        family=False,
    ),
    PRO: TariffInfo(
        code=PRO,
        title="PRO",
        price="99 ₽/мес",
        notes_limit=None,
        daily_advice=True,
        analytics=True,
        export=True,
        priority_ai=False,
        family=False,
    ),
    PREMIUM: TariffInfo(
        code=PREMIUM,
        title="PREMIUM",
        price="299 ₽/мес",
        notes_limit=None,
        daily_advice=True,
        analytics=True,
        export=True,
        priority_ai=True,
        family=True,
    ),
}


def get_tariff(code: str | None) -> TariffInfo:
    """Возвращаем инфо по тарифу, по умолчанию FREE."""
    return TARIFFS.get(code or FREE, TARIFFS[FREE])


def notes_left(tariff_code: str, current_count: int) -> int | None:
    """Сколько заметок ещё можно создать. None = безлимит."""
    info = get_tariff(tariff_code)
    if info.notes_limit is None:
        return None
    return max(0, info.notes_limit - current_count)


def can_add_note(tariff_code: str, current_count: int) -> bool:
    info = get_tariff(tariff_code)
    if info.notes_limit is None:
        return True
    return current_count < info.notes_limit
