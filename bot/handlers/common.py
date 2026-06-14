"""
Общие помощники для хендлеров: сборка текста заметки, сохранение
заметки с учётом лимита тарифа, создание напоминания + постановка в
планировщик.
"""
from __future__ import annotations

from datetime import datetime

from database.db import Database
from scheduler.reminders import ReminderScheduler
from utils.tariffs import can_add_note


def build_note_text(data: dict) -> str:
    """Собираем тело заметки из summary + ключевых фактов."""
    parts: list[str] = []
    if data.get("summary"):
        parts.append(str(data["summary"]))
    key_info = data.get("key_info") or []
    for item in key_info:
        parts.append(f"• {item}")
    text = "\n".join(parts).strip()
    return text or (data.get("title") or "Заметка")


def payload_from_image(data: dict) -> dict:
    """Нормализуем ответ анализа фото в единый payload для pending-хранилища."""
    return {
        "kind": "photo",
        "note_text": build_note_text(data),
        "title": data.get("title"),
        "type": data.get("type"),
        "category": data.get("category"),
        "tags": data.get("tags") or [],
        "deadline": data.get("deadline"),
        "reminder_text": data.get("suggested_reminder") or data.get("title")
        or data.get("summary"),
        "datetime": None,
        "repeat": "none",
    }


def payload_from_text(data: dict) -> dict:
    """Нормализуем ответ разбора текста/голоса."""
    return {
        "kind": "text",
        "intent": data.get("intent", "note"),
        "note_text": data.get("text") or data.get("title") or "",
        "title": data.get("title"),
        "type": data.get("type"),
        "category": data.get("category"),
        "tags": data.get("tags") or [],
        "deadline": None,
        "reminder_text": data.get("text") or data.get("title"),
        "datetime": data.get("datetime"),
        "repeat": data.get("repeat") or "none",
    }


async def save_note(db: Database, user_id: int, payload: dict) -> tuple[int | None, str]:
    """
    Сохраняем заметку с проверкой лимита тарифа.
    Возвращаем (id или None, code), где code: "ok" | "limit".
    """
    user = await db.get_user(user_id)
    tariff = user["tariff"] if user else "free"
    count = await db.count_notes(user_id)
    if not can_add_note(tariff, count):
        return None, "limit"

    tags = payload.get("tags") or []
    tags_str = ",".join(str(t) for t in tags) if tags else None
    note_id = await db.add_note(
        user_id=user_id,
        text=payload.get("note_text") or "",
        note_type=payload.get("type"),
        category=payload.get("category"),
        title=payload.get("title"),
        tags=tags_str,
    )
    return note_id, "ok"


async def create_reminder(
    db: Database,
    scheduler: ReminderScheduler,
    user_id: int,
    text: str,
    when: datetime,
    context: str | None = None,
    repeat: str = "none",
) -> int:
    """Создаём напоминание в БД и ставим задачу в планировщик."""
    reminder_id = await db.add_reminder(user_id, text, when, context, repeat)
    await scheduler.schedule(reminder_id)
    return reminder_id
