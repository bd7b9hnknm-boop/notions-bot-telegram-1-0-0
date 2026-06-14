"""Сбор всех роутеров в один список для подключения в main.py."""
from aiogram import Router

from bot.handlers import callbacks, commands, fallback, media, photo, text


def get_routers() -> list[Router]:
    # порядок важен: команды и медиа раньше «всеядного» текстового хендлера,
    # fallback — самый последний (ловит всё остальное)
    return [
        commands.router,
        callbacks.router,
        photo.router,
        media.router,
        text.router,
        fallback.router,
    ]
