"""
Inline-клавиатуры. Логика действий завязана на callback_data вида
"action:pid[:extra]", где pid — ключ во временном хранилище (pending).
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def after_analysis(
    pid: str,
    allow_remind: bool = True,
    direct_time_label: str | None = None,
) -> InlineKeyboardMarkup:
    """
    Кнопки под результатом анализа фото/текста.
    Если direct_time_label задан (мы поняли время из текста) — добавляем
    кнопку быстрого подтверждения этого времени.
    """
    kb = InlineKeyboardBuilder()
    if direct_time_label:
        kb.button(text=f"✅ Напомнить {direct_time_label}", callback_data=f"remset:{pid}")
    kb.button(text="💾 Сохранить заметку", callback_data=f"save:{pid}")
    if allow_remind:
        label = "⏰ Напомнить (другое время)" if direct_time_label else "⏰ Напомнить"
        kb.button(text=label, callback_data=f"rem:{pid}")
    kb.button(text="❌ Не надо", callback_data=f"cancel:{pid}")
    kb.adjust(1)
    return kb.as_markup()


def choose_time(pid: str, options: list[dict]) -> InlineKeyboardMarkup:
    """Кнопки выбора времени напоминания."""
    kb = InlineKeyboardBuilder()
    for opt in options:
        kb.button(text=opt["label"], callback_data=f"remat:{pid}:{opt['code']}")
    kb.button(text="✏️ Своё время", callback_data=f"custom:{pid}")
    kb.button(text="« Назад", callback_data=f"back:{pid}")
    kb.adjust(1)
    return kb.as_markup()


def reminder_fired(reminder_id: int) -> InlineKeyboardMarkup:
    """Кнопки под сработавшим напоминанием."""
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Сделал", callback_data=f"rdone:{reminder_id}")
    kb.button(text="😴 Отложить на час", callback_data=f"rsnooze:{reminder_id}")
    kb.adjust(2)
    return kb.as_markup()
