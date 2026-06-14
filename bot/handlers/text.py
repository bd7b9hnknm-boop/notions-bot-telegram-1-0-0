"""
Обработка обычных текстовых сообщений: понимаем, заметка это или
напоминание со временем, и предлагаем действия.

Этот роутер подключается последним — чтобы не перехватывать команды.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from ai.base import AIProvider
from bot import personality
from bot.handlers.intent import present_intent
from database.db import Database

router = Router(name="text")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message, db: Database, ai: AIProvider) -> None:
    await db.get_or_create_user(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    status = await message.answer(personality.thinking("сообщение"))
    await present_intent(status, db, ai, message.text)
