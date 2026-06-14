"""
Фоллбэк на неподдержанные типы сообщений (документы, стикеры, видео и пр.).
Регистрируется последним — ловит всё, что не разобрали другие хендлеры,
чтобы бот не «молчал».
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from bot import personality

router = Router(name="fallback")


@router.message(F.document)
async def on_document(message: Message) -> None:
    await message.answer(personality.unsupported("document"))


@router.message(F.sticker)
async def on_sticker(message: Message) -> None:
    await message.answer(personality.unsupported("sticker"))


@router.message(F.video | F.video_note | F.animation)
async def on_video(message: Message) -> None:
    await message.answer(personality.unsupported("video"))


@router.message()
async def on_other(message: Message) -> None:
    await message.answer(personality.unsupported("other"))
