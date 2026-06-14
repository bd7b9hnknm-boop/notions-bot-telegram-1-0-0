"""
Планировщик напоминаний на APScheduler.

- schedule()  — поставить напоминание на конкретное время;
- restore()   — при старте бота заново поставить все pending-напоминания
                из БД (планировщик держит задачи в памяти);
- _fire()     — отправить сообщение пользователю и пометить как done.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot import keyboards, personality
from database.db import Database
from utils.logger import get_logger
from utils.timeutils import TZ, now

logger = get_logger(__name__)


class ReminderScheduler:
    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
        self.scheduler = AsyncIOScheduler(timezone=TZ)

    def start(self) -> None:
        self.scheduler.start()
        logger.info("Планировщик запущен.")

    async def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)

    async def schedule(self, reminder_id: int, run_date: datetime) -> str:
        """Ставим задачу на время run_date. Возвращаем id задачи."""
        job = self.scheduler.add_job(
            self._fire,
            trigger="date",
            run_date=run_date,
            args=[reminder_id],
            id=f"rem_{reminder_id}",
            replace_existing=True,
            misfire_grace_time=3600,  # если бот «проспал» — всё равно отправим в течение часа
        )
        await self.db.set_reminder_job(reminder_id, job.id)
        return job.id

    async def cancel(self, reminder_id: int) -> None:
        try:
            self.scheduler.remove_job(f"rem_{reminder_id}")
        except Exception:
            pass  # задачи может уже не быть — это нормально

    async def restore(self) -> None:
        """При старте — перепланировать все ожидающие напоминания из БД."""
        rows = await self.db.list_all_pending()
        restored, overdue = 0, 0
        for r in rows:
            try:
                dt = datetime.fromisoformat(r["remind_at"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=TZ)
            except Exception:
                continue
            if dt <= now():
                # просроченное — отправим через 5 секунд после старта
                dt = now() + timedelta(seconds=5)
                overdue += 1
            await self.schedule(r["id"], dt)
            restored += 1
        if restored:
            logger.info("Восстановлено напоминаний: %s (из них просроченных: %s)",
                        restored, overdue)

    async def _fire(self, reminder_id: int) -> None:
        """Срабатывание напоминания: шлём сообщение и помечаем done."""
        reminder = await self.db.get_reminder(reminder_id)
        if not reminder or reminder["status"] != "pending":
            return
        try:
            await self.bot.send_message(
                reminder["user_id"],
                personality.reminder_fired(reminder["text"], reminder.get("context")),
                reply_markup=keyboards.reminder_fired(reminder_id),
            )
            await self.db.set_reminder_status(reminder_id, "done")
        except TelegramAPIError as e:
            logger.warning("Не смог отправить напоминание #%s: %s", reminder_id, e)
