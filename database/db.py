"""
Слой работы с базой данных (SQLite через aiosqlite).

Таблицы:
  users     — пользователи и их настройки/тариф
  notes     — заметки (тип, текст, теги, категория)
  reminders — напоминания (текст, время, статус, контекст)

Весь доступ к БД идёт через класс Database, чтобы не плодить
соединения и держать схему в одном месте.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import aiosqlite

from utils.logger import get_logger
from utils.tariffs import FREE

logger = get_logger(__name__)


# ------------------------------------------------------------------ SQL-схема
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    first_name  TEXT,
    tariff      TEXT NOT NULL DEFAULT 'free',
    timezone    TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    type        TEXT,
    category    TEXT,
    title       TEXT,
    text        TEXT NOT NULL,
    tags        TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    text        TEXT NOT NULL,
    context     TEXT,
    remind_at   TEXT NOT NULL,           -- ISO-время (в часовом поясе бота)
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending | done | cancelled
    job_id      TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id);
CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id);
CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    # ---------------------------------------------------------- жизненный цикл
    async def connect(self) -> None:
        # Создаём папку для файла БД, если её нет
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)

        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row  # доступ к колонкам по имени
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        logger.info("База данных готова: %s", self.path)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("База не подключена. Сначала вызови connect().")
        return self._conn

    # ----------------------------------------------------------------- users
    async def get_or_create_user(
        self, user_id: int, username: str | None, first_name: str | None
    ) -> dict[str, Any]:
        cur = await self.conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cur.fetchone()
        if row:
            return dict(row)

        await self.conn.execute(
            "INSERT INTO users (user_id, username, first_name, tariff, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, username, first_name, FREE, datetime.now().isoformat()),
        )
        await self.conn.commit()
        cur = await self.conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cur.fetchone()
        logger.info("Новый пользователь: %s (%s)", user_id, username)
        return dict(row)

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        cur = await self.conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def set_tariff(self, user_id: int, tariff: str) -> None:
        await self.conn.execute(
            "UPDATE users SET tariff = ? WHERE user_id = ?", (tariff, user_id)
        )
        await self.conn.commit()

    # ----------------------------------------------------------------- notes
    async def add_note(
        self,
        user_id: int,
        text: str,
        note_type: str | None = None,
        category: str | None = None,
        title: str | None = None,
        tags: str | None = None,
    ) -> int:
        cur = await self.conn.execute(
            "INSERT INTO notes (user_id, type, category, title, text, tags, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, note_type, category, title, text, tags,
             datetime.now().isoformat()),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def count_notes(self, user_id: int) -> int:
        cur = await self.conn.execute(
            "SELECT COUNT(*) AS c FROM notes WHERE user_id = ?", (user_id,)
        )
        row = await cur.fetchone()
        return row["c"] if row else 0

    async def list_notes(self, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT * FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def search_notes(
        self, user_id: int, query: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        like = f"%{query}%"
        cur = await self.conn.execute(
            "SELECT * FROM notes WHERE user_id = ? "
            "AND (text LIKE ? OR title LIKE ? OR tags LIKE ? OR category LIKE ?) "
            "ORDER BY id DESC LIMIT ?",
            (user_id, like, like, like, like, limit),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_note(self, note_id: int, user_id: int) -> dict[str, Any] | None:
        cur = await self.conn.execute(
            "SELECT * FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def delete_note(self, note_id: int, user_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------- reminders
    async def add_reminder(
        self,
        user_id: int,
        text: str,
        remind_at: datetime,
        context: str | None = None,
    ) -> int:
        cur = await self.conn.execute(
            "INSERT INTO reminders (user_id, text, context, remind_at, status, created_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?)",
            (user_id, text, context, remind_at.isoformat(),
             datetime.now().isoformat()),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def set_reminder_job(self, reminder_id: int, job_id: str) -> None:
        await self.conn.execute(
            "UPDATE reminders SET job_id = ? WHERE id = ?", (job_id, reminder_id)
        )
        await self.conn.commit()

    async def get_reminder(self, reminder_id: int) -> dict[str, Any] | None:
        cur = await self.conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def list_pending_reminders(self, user_id: int) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT * FROM reminders WHERE user_id = ? AND status = 'pending' "
            "ORDER BY remind_at ASC",
            (user_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def list_all_pending(self) -> list[dict[str, Any]]:
        """Все ожидающие напоминания — нужно при старте, чтобы заново запланировать."""
        cur = await self.conn.execute(
            "SELECT * FROM reminders WHERE status = 'pending'"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def set_reminder_status(self, reminder_id: int, status: str) -> None:
        await self.conn.execute(
            "UPDATE reminders SET status = ? WHERE id = ?", (status, reminder_id)
        )
        await self.conn.commit()

    async def update_reminder_time(
        self, reminder_id: int, remind_at: datetime
    ) -> None:
        await self.conn.execute(
            "UPDATE reminders SET remind_at = ?, status = 'pending' WHERE id = ?",
            (remind_at.isoformat(), reminder_id),
        )
        await self.conn.commit()

    # ------------------------------------------------------------- analytics
    async def stats(self, user_id: int) -> dict[str, int]:
        """Простая статистика для раздела аналитики (PRO)."""
        notes = await self.count_notes(user_id)
        cur = await self.conn.execute(
            "SELECT status, COUNT(*) AS c FROM reminders WHERE user_id = ? GROUP BY status",
            (user_id,),
        )
        rows = await cur.fetchall()
        by_status = {r["status"]: r["c"] for r in rows}
        return {
            "notes": notes,
            "reminders_pending": by_status.get("pending", 0),
            "reminders_done": by_status.get("done", 0),
            "reminders_cancelled": by_status.get("cancelled", 0),
        }
