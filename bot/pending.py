"""
Временное хранилище разобранных данных между сообщением и нажатием кнопки.

Когда бот показал результат анализа с кнопками, сами данные (текст,
дедлайн, теги) надо где-то держать до нажатия. Кладём их сюда под
коротким id, который влезает в callback_data (лимит Telegram — 64 байта).

Хранилище в памяти: при перезапуске «черновики» теряются — это ок,
сохранённые заметки и напоминания живут в БД.
"""
from __future__ import annotations

import uuid
from typing import Any

_store: dict[str, dict[str, Any]] = {}


def put(data: dict[str, Any]) -> str:
    pid = uuid.uuid4().hex[:10]
    _store[pid] = data
    return pid


def get(pid: str) -> dict[str, Any] | None:
    return _store.get(pid)


def pop(pid: str) -> dict[str, Any] | None:
    return _store.pop(pid, None)
