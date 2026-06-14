"""
Общий разбор «намерения» из текста (и из расшифрованного голоса):
заметка это или напоминание (в т.ч. повторяющееся).
"""
from __future__ import annotations

from aiogram.types import Message

from ai.base import AIProvider
from ai.gemini import AIError
from bot import keyboards, pending, personality
from bot.handlers.common import payload_from_text
from database.db import Database
from utils import timeutils
from utils.logger import get_logger

logger = get_logger(__name__)


async def present_intent(status: Message, db: Database, ai: AIProvider, raw_text: str) -> None:
    """Разбираем текст и показываем результат с кнопками действий."""
    try:
        data = await ai.analyze_text(raw_text)
    except AIError as e:
        logger.warning("Разбор текста не удался: %s", e)
        await status.edit_text(
            "Хм, не понял 🤔 Попробуй сформулировать иначе — или пришли как заметку."
        )
        return

    payload = payload_from_text(data)
    payload["display"] = personality.format_text_intent(data)
    payload["saved"] = None
    payload["reminded"] = None

    # время + повтор для кнопки быстрого подтверждения
    direct_label = None
    repeat = payload.get("repeat") or "none"
    dt = timeutils.parse_deadline(payload.get("datetime"))
    if payload.get("intent") == "reminder" and dt and dt > timeutils.now():
        payload["datetime"] = dt.isoformat()
        direct_label = timeutils.describe_schedule(repeat, dt)
    else:
        payload["datetime"] = None

    pid = pending.put(payload)
    await status.edit_text(
        personality.render_card(payload),
        reply_markup=keyboards.after_analysis(pid, payload, direct_label),
    )
