"""
Обработка фото: скачиваем картинку, отправляем в ИИ на анализ,
показываем разобранный результат с кнопками действий.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from ai.base import AIProvider
from ai.gemini import AIError
from bot import keyboards, pending, personality
from bot.handlers.common import payload_from_image
from database.db import Database
from utils.logger import get_logger

router = Router(name="photo")
logger = get_logger(__name__)


@router.message(F.photo)
async def handle_photo(message: Message, db: Database, ai: AIProvider) -> None:
    await db.get_or_create_user(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )

    await message.bot.send_chat_action(message.chat.id, "typing")
    status = await message.answer(personality.thinking("фото"))

    # самое крупное доступное превью
    photo = message.photo[-1]
    try:
        file = await message.bot.get_file(photo.file_id)
        buf = await message.bot.download_file(file.file_path)
        image_bytes = buf.read()
    except Exception:
        logger.exception("Не удалось скачать фото")
        await status.edit_text("Не смог скачать фото 😕 Пришли ещё раз, пожалуйста.")
        return

    try:
        data = await ai.analyze_image(image_bytes, mime_type="image/jpeg")
    except AIError as e:
        logger.warning("Анализ фото не удался: %s", e)
        await status.edit_text(
            "Не получилось разобрать фото 😕 Попробуй сфотографировать почётче "
            "или пришли другое."
        )
        return

    payload = payload_from_image(data)
    payload["display"] = personality.format_analysis(data)
    payload["saved"] = None
    payload["reminded"] = None
    pid = pending.put(payload)

    await status.edit_text(
        personality.render_card(payload),
        reply_markup=keyboards.after_analysis(pid, payload),
    )
