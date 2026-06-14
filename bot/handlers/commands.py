"""
Команды и кнопки нижней клавиатуры:
/start /help /menu /today /notes /find /del /reminders /sovet /stats
/upgrade /setplan
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from ai.base import AIProvider
from bot import keyboards, personality, views
from config import settings
from database.db import Database
from utils.tariffs import VALID_TARIFFS, get_tariff

router = Router(name="commands")


def _is_admin(user_id: int) -> bool:
    return (not settings.admin_ids) or (user_id in settings.admin_ids)


# ------------------------------------------------------------------ старт/меню
@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    u = message.from_user
    await db.get_or_create_user(u.id, u.username, u.first_name)
    await message.answer(personality.greeting(u.first_name),
                         reply_markup=keyboards.main_reply())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(personality.help_text())


@router.message(Command("menu"))
@router.message(F.text == keyboards.BTN_MENU)
async def cmd_menu(message: Message) -> None:
    await message.answer(personality.menu_text(),
                         reply_markup=keyboards.main_menu_inline())


# ------------------------------------------------------------------ агенда
@router.message(Command("today"))
@router.message(F.text == keyboards.BTN_TODAY)
async def cmd_today(message: Message, db: Database) -> None:
    text, kb = await views.today_view(db, message.from_user.id)
    await message.answer(text, reply_markup=kb)


# ------------------------------------------------------------------ заметки
@router.message(Command("notes"))
@router.message(F.text == keyboards.BTN_NOTES)
async def cmd_notes(message: Message, db: Database) -> None:
    text, kb = await views.notes_view(db, message.from_user.id)
    await message.answer(text, reply_markup=kb)


@router.message(Command("find"))
async def cmd_find(message: Message, command: CommandObject, db: Database) -> None:
    query = (command.args or "").strip()
    if not query:
        await message.answer("Что ищем? Напиши: <code>/find квитанция</code>")
        return
    notes = await db.search_notes(message.from_user.id, query, limit=20)
    kb = keyboards.notes_list(notes) if notes else None
    await message.answer(personality.format_search_results(query, notes), reply_markup=kb)


@router.message(Command("del"))
async def cmd_del(message: Message, command: CommandObject, db: Database) -> None:
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer("Удобнее удалять через /notes → открыть заметку → 🗑. "
                             "Или: <code>/del 12</code>")
        return
    ok = await db.delete_note(int(arg), message.from_user.id)
    await message.answer(personality.note_deleted() if ok else "Не нашёл такую заметку.")


# ------------------------------------------------------------------ напоминания
@router.message(Command("reminders"))
@router.message(F.text == keyboards.BTN_REMINDERS)
async def cmd_reminders(message: Message, db: Database) -> None:
    text, kb = await views.reminders_view(db, message.from_user.id)
    await message.answer(text, reply_markup=kb)


# ------------------------------------------------------------------ совет (PRO)
@router.message(Command("sovet"))
@router.message(F.text == keyboards.BTN_ADVICE)
async def cmd_sovet(message: Message, db: Database, ai: AIProvider) -> None:
    u = message.from_user
    user = await db.get_or_create_user(u.id, u.username, u.first_name)
    if not get_tariff(user["tariff"]).daily_advice:
        await message.answer(personality.upsell("Совет дня"))
        return
    status = await message.answer("Думаю над советом… 🤔")
    advice = await views.sovet_view(db, ai, user)
    await status.edit_text(advice)


# ------------------------------------------------------------------ аналитика (PRO)
@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database) -> None:
    u = message.from_user
    user = await db.get_or_create_user(u.id, u.username, u.first_name)
    if not get_tariff(user["tariff"]).analytics:
        await message.answer(personality.upsell("Аналитика продуктивности"))
        return
    s = await db.stats(user["user_id"])
    await message.answer(
        "<b>Твоя продуктивность</b> 📊\n\n"
        f"📝 Заметок: <b>{s['notes']}</b>\n"
        f"⏰ Активных напоминаний: <b>{s['reminders_pending']}</b>\n"
        f"✅ Выполнено: <b>{s['reminders_done']}</b>\n"
        f"🚫 Отменено: <b>{s['reminders_cancelled']}</b>"
    )


# ------------------------------------------------------------------ тарифы
@router.message(Command("upgrade"))
async def cmd_upgrade(message: Message, db: Database) -> None:
    u = message.from_user
    user = await db.get_or_create_user(u.id, u.username, u.first_name)
    text, _ = views.upgrade_view(user["tariff"])
    await message.answer(text)


@router.message(Command("setplan"))
async def cmd_setplan(message: Message, command: CommandObject, db: Database) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("Эта команда только для админа.")
        return
    plan = (command.args or "").strip().lower()
    if plan not in VALID_TARIFFS:
        await message.answer("Укажи тариф: <code>/setplan free|pro|premium</code>")
        return
    u = message.from_user
    await db.get_or_create_user(u.id, u.username, u.first_name)
    await db.set_tariff(u.id, plan)
    await message.answer(f"Готово. Твой тариф теперь: <b>{get_tariff(plan).title}</b> ✅")
