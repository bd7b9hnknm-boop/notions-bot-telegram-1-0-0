"""
Работа со временем: текущее время в часовом поясе бота, разбор
человеческих формулировок ("завтра в 18:00") и умные предложения
времени для напоминаний.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import dateparser

from config import settings

TZ = ZoneInfo(settings.timezone)

# "в 9", "к 18", "на 7" -> "в 9:00" (dateparser плохо понимает голый час)
_BARE_HOUR = re.compile(r"\b(в|во|к|на)\s+(\d{1,2})(?!\s*[:.\d])", re.IGNORECASE)


def now() -> datetime:
    """Текущее время в часовом поясе бота (timezone-aware)."""
    return datetime.now(TZ)


def _normalize(text: str) -> str:
    """Приводим частые формулировки к виду, понятному dateparser."""
    return _BARE_HOUR.sub(r"\1 \2:00", text)


def parse_human(text: str, base: datetime | None = None) -> datetime | None:
    """
    Разбираем свободный текст в дату/время.
    Примеры: "завтра в 9", "через 2 часа", "25 числа в 18:00", "в пятницу".
    Возвращаем aware-datetime в TZ бота или None.
    """
    base = base or now()
    dt = dateparser.parse(
        _normalize(text),
        languages=["ru", "en"],
        settings={
            "PREFER_DATES_FROM": "future",   # "в 9" -> ближайшие будущие 9
            "RELATIVE_BASE": base.replace(tzinfo=None),
            "RETURN_AS_TIMEZONE_AWARE": False,
        },
    )
    if dt is None:
        return None
    # привязываем к нашему часовому поясу
    return dt.replace(tzinfo=TZ)


def parse_deadline(value: str | None) -> datetime | None:
    """Разбор поля deadline/datetime, пришедшего от ИИ (ISO или человеческий текст)."""
    if not value or str(value).lower() in {"null", "none", ""}:
        return None
    val = str(value).strip()
    # сперва пробуем строгий ISO
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(val, fmt)
            return dt.replace(tzinfo=TZ)
        except ValueError:
            continue
    # иначе — человеческий разбор
    return parse_human(val)


def suggested_times(deadline: datetime | None = None) -> list[dict]:
    """
    Возвращаем список умных вариантов времени для inline-кнопок:
    [{"code": ..., "label": ..., "dt": datetime}, ...]
    """
    n = now()
    options: list[dict] = []

    # Через час / через 3 часа
    options.append({"code": "h1", "label": "⏱ Через час", "dt": n + timedelta(hours=1)})
    options.append({"code": "h3", "label": "⏱ Через 3 часа", "dt": n + timedelta(hours=3)})

    # Сегодня вечером в 19:00 (или завтра, если уже поздно)
    eve = n.replace(hour=19, minute=0, second=0, microsecond=0)
    if eve <= n:
        eve += timedelta(days=1)
        label_eve = "🌆 Завтра в 19:00"
    else:
        label_eve = "🌆 Сегодня в 19:00"
    options.append({"code": "eve", "label": label_eve, "dt": eve})

    # Завтра утром в 9:00
    morn = (n + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    options.append({"code": "morn", "label": "☀️ Завтра в 9:00", "dt": morn})

    # За день до дедлайна в 19:00 (если дедлайн есть и он в будущем)
    if deadline and deadline > n:
        pre = (deadline - timedelta(days=1)).replace(
            hour=19, minute=0, second=0, microsecond=0
        )
        if pre > n:
            options.append({"code": "predeadline", "label": "📌 За день до дедлайна", "dt": pre})

    return options


def fmt(dt: datetime) -> str:
    """Красивый вывод времени для пользователя."""
    months = ["янв", "фев", "мар", "апр", "мая", "июн",
              "июл", "авг", "сен", "окт", "ноя", "дек"]
    return f"{dt.day} {months[dt.month - 1]} в {dt.strftime('%H:%M')}"


# «каждый/каждую/каждое <день>» с правильным родом
_EVERY_WEEKDAY = ["каждый понедельник", "каждый вторник", "каждую среду",
                  "каждый четверг", "каждую пятницу", "каждую субботу",
                  "каждое воскресенье"]


def describe_schedule(repeat: str, dt: datetime) -> str:
    """Человеческое описание расписания напоминания."""
    t = dt.strftime("%H:%M")
    if repeat == "daily":
        return f"каждый день в {t}"
    if repeat == "weekdays":
        return f"по будням в {t}"
    if repeat == "weekly":
        return f"{_EVERY_WEEKDAY[dt.weekday()]} в {t}"
    if repeat == "monthly":
        return f"каждое {dt.day}-е число в {t}"
    return fmt(dt)  # разовое


def is_recurring_today(repeat: str, dt: datetime, ref: datetime | None = None) -> bool:
    """Срабатывает ли повторяющееся напоминание сегодня (для агенды)."""
    ref = ref or now()
    if repeat == "daily":
        return True
    if repeat == "weekdays":
        return ref.weekday() < 5
    if repeat == "weekly":
        return ref.weekday() == dt.weekday()
    if repeat == "monthly":
        return ref.day == dt.day
    return False
