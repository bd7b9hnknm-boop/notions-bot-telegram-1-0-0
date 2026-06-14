"""
Планировщик напоминаний на APScheduler.

Поддерживает разовые и повторяющиеся напоминания:
- none     -> разовая дата (DateTrigger);
- daily    -> каждый день в нужное время (cron);
- weekdays -> по будням (пн-пт);
- weekly   -> раз в неделю в тот же день недели;
- monthly  -> раз в месяц в то же число.

schedule() сам читает напоминание из БД и выбирает нужный триггер.
restore() при старте заново ставит все pending-напоминания.
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

_WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


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

    @staticmethod
    def _parse(dt_str: str) -> datetime:
        dt = datetime.fromisoformat(dt_str)
        return dt if dt.tzinfo else dt.replace(tzinfo=TZ)

    async def schedule(self, reminder_id: int) -> str | None:
        """Поставить напоминание в планировщик (триггер выбираем по repeat)."""
        r = await self.db.get_reminder(reminder_id)
        if not r or r["status"] != "pending":
            return None

        dt = self._parse(r["remind_at"])
        repeat = r.get("repeat") or "none"
        job_id = f"rem_{reminder_id}"

        if repeat == "none":
            run = dt if dt > now() else now() + timedelta(seconds=5)
            self.scheduler.add_job(
                self._fire, "date", run_date=run, args=[reminder_id],
                id=job_id, replace_existing=True, misfire_grace_time=3600,
            )
        else:
            kw: dict = {"hour": dt.hour, "minute": dt.minute}
            if repeat == "weekdays":
                kw["day_of_week"] = "mon-fri"
            elif repeat == "weekly":
                kw["day_of_week"] = _WEEKDAY_NAMES[dt.weekday()]
            elif repeat == "monthly":
                kw["day"] = dt.day
            # daily -> только hour/minute
            self.scheduler.add_job(
                self._fire, "cron", args=[reminder_id],
                id=job_id, replace_existing=True, misfire_grace_time=3600, **kw,
            )

        await self.db.set_reminder_job(reminder_id, job_id)
        return job_id

    async def cancel(self, reminder_id: int) -> None:
        try:
            self.scheduler.remove_job(f"rem_{reminder_id}")
        except Exception:
            pass  # задачи может уже не быть — это нормально

    async def restore(self) -> None:
        """При старте — заново поставить все ожидающие напоминания из БД."""
        rows = await self.db.list_all_pending()
        restored = 0
        for r in rows:
            try:
                await self.schedule(r["id"])
                restored += 1
            except Exception:
                logger.exception("Не смог восстановить напоминание #%s", r.get("id"))
        if restored:
            logger.info("Восстановлено напоминаний: %s", restored)

    async def _fire(self, reminder_id: int) -> None:
        """Срабатывание напоминания: шлём сообщение; разовое помечаем done."""
        reminder = await self.db.get_reminder(reminder_id)
        if not reminder or reminder["status"] != "pending":
            return
        repeat = reminder.get("repeat") or "none"
        try:
            await self.bot.send_message(
                reminder["user_id"],
                personality.reminder_fired(
                    reminder["text"], reminder.get("context"), repeat
                ),
                reply_markup=keyboards.reminder_fired(reminder_id, repeat),
            )
            if repeat == "none":
                await self.db.set_reminder_status(reminder_id, "done")
        except TelegramAPIError as e:
            logger.warning("Не смог отправить напоминание #%s: %s", reminder_id, e)
