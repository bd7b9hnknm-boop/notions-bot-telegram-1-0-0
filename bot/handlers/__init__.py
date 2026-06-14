"""Сбор всех роутеров в один список для подключения в main.py."""
from aiogram import Router

from bot.handlers import callbacks, commands, media, photo, text


def get_routers() -> list[Router]:
    # порядок важен: команды и медиа раньше «всеядного» текстового хендлера
    return [
        commands.router,
        callbacks.router,
        photo.router,
        media.router,
        text.router,
    ]
