"""
Обработка голосовых сообщений: скачиваем аудио, расшифровываем через
ИИ в текст, а дальше разбираем как обычное намерение (заметка/напоминание).
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from ai.base import AIProvider
from ai.gemini import AIError
from bot import personality
from bot.handlers.intent import present_intent
from database.db import Database
from utils.logger import get_logger

router = Router(name="media")
logger = get_logger(__name__)


@router.message(F.voice)
async def handle_voice(message: Message, db: Database, ai: AIProvider) -> None:
    await db.get_or_create_user(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    await message.bot.send_chat_action(message.chat.id, "typing")
    status = await message.answer(personality.thinking("голосовое"))

    try:
        file = await message.bot.get_file(message.voice.file_id)
        buf = await message.bot.download_file(file.file_path)
        audio_bytes = buf.read()
    except Exception:
        logger.exception("Не удалось скачать голосовое")
        await status.edit_text("Не смог скачать голосовое 😕 Пришли ещё раз.")
        return

    try:
        text = await ai.transcribe_audio(audio_bytes, mime_type="audio/ogg")
    except AIError as e:
        logger.warning("Расшифровка не удалась: %s", e)
        await status.edit_text("Не разобрал голосовое 😕 Попробуй ещё раз или напиши текстом.")
        return

    if not text.strip():
        await status.edit_text("Кажется, там тишина 🤫 Попробуй ещё раз.")
        return

    # показываем расшифровку и разбираем намерение
    await status.edit_text(f"🎤 Расслышал: «{personality.e(text)}»\n\nРазбираю…")
    await present_intent(status, db, ai, text)
