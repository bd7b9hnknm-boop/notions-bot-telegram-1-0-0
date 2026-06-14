"""
Общие хелперы для всех ИИ-провайдеров: подсказка текущей даты и
надёжный разбор JSON из ответа модели.
"""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from ai.errors import AIError
from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)


def today_hint() -> str:
    """Подсказка модели про текущую дату — чтобы корректно понимать «завтра» и т.п."""
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    weekdays = ["понедельник", "вторник", "среда", "четверг",
                "пятница", "суббота", "воскресенье"]
    return (f"Сегодня: {now.strftime('%Y-%m-%d %H:%M')} "
            f"({weekdays[now.weekday()]}), часовой пояс {settings.timezone}.")


def extract_json(text: str) -> dict:
    """Достаём JSON из ответа модели, аккуратно срезая возможные ```-обёртки."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    # на случай мусора по краям — берём от первой { до последней }
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start:end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Не удалось разобрать JSON от модели: %s | %r", e, text[:300])
        raise AIError("Модель вернула ответ в неожиданном формате.") from e
