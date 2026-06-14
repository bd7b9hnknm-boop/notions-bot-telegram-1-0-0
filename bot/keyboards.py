"""
Клавиатуры бота.

Inline-действия кодируются в callback_data как "action:...".
Для выбора времени используется единый «target»:
  d_<pid>  — черновик (pending) после разбора;
  r_<rid>  — уже существующее напоминание (перенос времени).
"""
from __future__ import annotations

from aiogram.types import (InlineKeyboardMarkup, KeyboardButton,
                           ReplyKeyboardMarkup)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# --- подписи кнопок нижней клавиатуры (должны совпадать с хендлерами) ---
BTN_TODAY = "📅 Сегодня"
BTN_NOTES = "📝 Заметки"
BTN_REMINDERS = "⏰ Напоминания"
BTN_ADVICE = "💡 Совет"
BTN_MENU = "⚙️ Меню"


# ============================================================ нижняя клавиатура
def main_reply() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text=BTN_TODAY)
    kb.button(text=BTN_NOTES)
    kb.button(text=BTN_REMINDERS)
    kb.button(text=BTN_ADVICE)
    kb.button(text=BTN_MENU)
    kb.adjust(2, 2, 1)
    return kb.as_markup(resize_keyboard=True, is_persistent=True)


def main_menu_inline() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Сегодня", callback_data="menu:today")
    kb.button(text="📝 Заметки", callback_data="menu:notes")
    kb.button(text="⏰ Напоминания", callback_data="menu:reminders")
    kb.button(text="💡 Совет дня", callback_data="menu:sovet")
    kb.button(text="💎 Тарифы", callback_data="menu:upgrade")
    kb.button(text="❓ Помощь", callback_data="menu:help")
    kb.adjust(2, 2, 2)
    return kb.as_markup()


# ============================================================ карточка разбора
def after_analysis(pid: str, payload: dict, direct_time_label: str | None = None) -> InlineKeyboardMarkup:
    """Кнопки под разбором. Учитывают, что уже сделано (saved/reminded)."""
    kb = InlineKeyboardBuilder()
    saved = bool(payload.get("saved"))
    reminded = bool(payload.get("reminded"))

    if direct_time_label and not reminded:
        kb.button(text=f"✅ Напомнить {direct_time_label}", callback_data=f"remset:{pid}")
    if not saved:
        kb.button(text="💾 Сохранить заметку", callback_data=f"save:{pid}")
    if not reminded:
        label = "⏰ Напомнить (другое время)" if direct_time_label else "⏰ Напомнить"
        kb.button(text=label, callback_data=f"rem:{pid}")

    if saved or reminded:
        kb.button(text="✅ Готово", callback_data=f"done:{pid}")
    else:
        kb.button(text="❌ Не надо", callback_data=f"cancel:{pid}")
    kb.adjust(1)
    return kb.as_markup()


# ============================================================ выбор времени
def choose_time(target: str, options: list[dict]) -> InlineKeyboardMarkup:
    """target = 'd_<pid>' (черновик) или 'r_<rid>' (перенос напоминания)."""
    kb = InlineKeyboardBuilder()
    for opt in options:
        kb.button(text=opt["label"], callback_data=f"tset:{target}:{opt['code']}")
    kb.button(text="✏️ Своё время", callback_data=f"tcustom:{target}")
    kb.button(text="« Назад", callback_data=f"tback:{target}")
    kb.adjust(1)
    return kb.as_markup()


# ============================================================ заметки
def notes_list(notes: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for n in notes:
        title = n.get("title") or (n.get("text") or "")[:35] or "Заметка"
        cat = f" · {n['category']}" if n.get("category") else ""
        kb.button(text=f"📝 {title}{cat}"[:60], callback_data=f"note:{n['id']}")
    kb.adjust(1)
    return kb.as_markup()


def note_manage(note_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⏰ Напомнить об этом", callback_data=f"nrem:{note_id}")
    kb.button(text="🗑 Удалить", callback_data=f"ndel:{note_id}")
    kb.button(text="« К списку", callback_data="nlist")
    kb.adjust(1)
    return kb.as_markup()


def confirm_delete(note_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Да, удалить", callback_data=f"ndelyes:{note_id}")
    kb.button(text="« Отмена", callback_data=f"note:{note_id}")
    kb.adjust(2)
    return kb.as_markup()


# ============================================================ напоминания
def reminders_list(reminders: list[dict], line_fn) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for r in reminders:
        kb.button(text=line_fn(r)[:60], callback_data=f"rmanage:{r['id']}")
    kb.adjust(1)
    return kb.as_markup()


def reminder_manage(reminder_id: int, recurring: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if recurring:
        kb.button(text="🕒 Изменить время", callback_data=f"rresched:{reminder_id}")
        kb.button(text="🔕 Отключить", callback_data=f"rcancel:{reminder_id}")
    else:
        kb.button(text="✅ Выполнить", callback_data=f"rdone:{reminder_id}")
        kb.button(text="🕒 Перенести", callback_data=f"rresched:{reminder_id}")
        kb.button(text="❌ Отменить", callback_data=f"rcancel:{reminder_id}")
    kb.button(text="« К списку", callback_data="rlist")
    kb.adjust(1)
    return kb.as_markup()


def reminder_fired(reminder_id: int, repeat: str = "none") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if repeat != "none":
        kb.button(text="👍 Ок", callback_data=f"rack:{reminder_id}")
        kb.button(text="🔕 Отключить повтор", callback_data=f"rcancel:{reminder_id}")
    else:
        kb.button(text="✅ Сделал", callback_data=f"rdone:{reminder_id}")
        kb.button(text="😴 Отложить", callback_data=f"rsnooze:{reminder_id}")
    kb.adjust(2)
    return kb.as_markup()


def snooze_menu(reminder_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="10 минут", callback_data=f"rsnoozeat:{reminder_id}:m10")
    kb.button(text="1 час", callback_data=f"rsnoozeat:{reminder_id}:h1")
    kb.button(text="3 часа", callback_data=f"rsnoozeat:{reminder_id}:h3")
    kb.button(text="🌆 Вечером", callback_data=f"rsnoozeat:{reminder_id}:eve")
    kb.button(text="☀️ Завтра утром", callback_data=f"rsnoozeat:{reminder_id}:morn")
    kb.adjust(3, 2)
    return kb.as_markup()
