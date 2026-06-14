"""
Точка входа.

Поднимаем бота: настройки -> логирование -> БД -> ИИ -> планировщик ->
роутеры -> polling. Зависимости (db, ai, scheduler) прокидываем в хендлеры
через start_polling — aiogram сам подставит их по имени аргумента.
"""
from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from ai.provider import get_provider
from bot.handlers import get_routers
from config import settings
from database.db import Database
from scheduler.reminders import ReminderScheduler
from utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


async def set_commands(bot: Bot) -> None:
    """Меню команд в Telegram (кнопка «/» в поле ввода)."""
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск и приветствие"),
        BotCommand(command="notes", description="Мои заметки"),
        BotCommand(command="find", description="Поиск по заметкам"),
        BotCommand(command="reminders", description="Мои напоминания"),
        BotCommand(command="sovet", description="Совет дня (PRO)"),
        BotCommand(command="stats", description="Аналитика (PRO)"),
        BotCommand(command="upgrade", description="Тарифы"),
        BotCommand(command="help", description="Справка"),
    ])


async def main() -> None:
    setup_logging()
    settings.validate()  # упадём с понятной ошибкой, если .env не заполнен

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Инфраструктура
    db = Database(settings.database_path)
    await db.connect()
    ai = get_provider()
    scheduler = ReminderScheduler(bot, db)

    # Роутеры
    for router in get_routers():
        dp.include_router(router)

    # Планировщик: запускаем и восстанавливаем напоминания из БД
    scheduler.start()
    await scheduler.restore()

    await set_commands(bot)
    logger.info("Бот «%s» запущен. Провайдер ИИ: %s", settings.bot_name, settings.ai_provider)

    try:
        await dp.start_polling(bot, db=db, ai=ai, scheduler=scheduler)
    finally:
        await scheduler.shutdown()
        await db.close()
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
