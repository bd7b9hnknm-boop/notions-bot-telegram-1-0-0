"""
Сборка экранов (текст + клавиатура) в одном месте, чтобы команды
и кнопки меню показывали одинаково.
"""
from __future__ import annotations

from datetime import datetime

from aiogram.types import InlineKeyboardMarkup

from ai.base import AIProvider
from ai.gemini import AIError
from bot import keyboards, personality
from database.db import Database
from utils import timeutils
from utils.tariffs import get_tariff


async def notes_view(db: Database, user_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    notes = await db.list_notes(user_id, limit=20)
    text = personality.format_notes_list(notes)
    kb = keyboards.notes_list(notes) if notes else None
    return text, kb


async def reminders_view(db: Database, user_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    reminders = await db.list_pending_reminders(user_id)
    text = personality.format_reminders_list(reminders)
    kb = keyboards.reminders_list(reminders, personality.reminder_line) if reminders else None
    return text, kb


async def today_view(db: Database, user_id: int) -> tuple[str, None]:
    reminders = await db.list_pending_reminders(user_id)
    one_off, recurring = [], []
    ref = timeutils.now()
    today = ref.date()
    for r in reminders:
        repeat = r.get("repeat") or "none"
        try:
            dt = datetime.fromisoformat(r["remind_at"])
        except Exception:
            continue
        if repeat == "none":
            if dt.date() == today:
                one_off.append(r)
        elif timeutils.is_recurring_today(repeat, dt, ref):
            recurring.append(r)
    notes_today = await db.count_notes_today(user_id)
    return personality.today_text(one_off, recurring, notes_today), None


def upgrade_view(tariff: str) -> tuple[str, None]:
    return personality.upgrade_text(tariff), None


async def sovet_view(db: Database, ai: AIProvider, user: dict) -> str:
    """Совет дня (PRO). Возвращает готовый текст."""
    if not get_tariff(user["tariff"]).daily_advice:
        return personality.upsell("Совет дня")

    notes = await db.list_notes(user["user_id"], limit=10)
    reminders = await db.list_pending_reminders(user["user_id"])
    ctx = ["Последние заметки:"]
    ctx += [f"- {n.get('title') or (n.get('text') or '')[:50]}" for n in notes] or ["(нет)"]
    ctx.append("Ближайшие напоминания:")
    ctx += [f"- {r['text']} ({r['remind_at']})" for r in reminders] or ["(нет)"]
    try:
        return await ai.daily_advice("\n".join(ctx))
    except AIError:
        return "Что-то я задумался 🤔 Попробуй ещё разок чуть позже."
