"""
Команды бота: /start, /help, /notes, /find, /reminders, /del,
/sovet (PRO), /stats (PRO), /upgrade, /setplan (для теста/админа).
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from ai.base import AIProvider
from ai.gemini import AIError
from bot import personality
from config import settings
from database.db import Database
from utils import timeutils
from utils.tariffs import VALID_TARIFFS, get_tariff

router = Router(name="commands")


def _is_admin(user_id: int) -> bool:
    """Админ — если он в списке ADMIN_IDS, либо список пуст (режим разработки)."""
    return (not settings.admin_ids) or (user_id in settings.admin_ids)


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    user = message.from_user
    await db.get_or_create_user(user.id, user.username, user.first_name)
    await message.answer(personality.greeting(user.first_name))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(personality.help_text())


@router.message(Command("upgrade"))
async def cmd_upgrade(message: Message, db: Database) -> None:
    user = await db.get_or_create_user(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    await message.answer(personality.upgrade_text(user["tariff"]))


@router.message(Command("notes"))
async def cmd_notes(message: Message, db: Database) -> None:
    notes = await db.list_notes(message.from_user.id, limit=15)
    await message.answer(personality.format_notes_list(notes))


@router.message(Command("find"))
async def cmd_find(message: Message, command: CommandObject, db: Database) -> None:
    query = (command.args or "").strip()
    if not query:
        await message.answer("Что ищем? Напиши: <code>/find квитанция</code>")
        return
    notes = await db.search_notes(message.from_user.id, query, limit=15)
    await message.answer(personality.format_search_results(query, notes))


@router.message(Command("del"))
async def cmd_del(message: Message, command: CommandObject, db: Database) -> None:
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer("Укажи номер заметки: <code>/del 12</code>")
        return
    ok = await db.delete_note(int(arg), message.from_user.id)
    await message.answer("Удалил. 🗑️" if ok else "Не нашёл такую заметку.")


@router.message(Command("reminders"))
async def cmd_reminders(message: Message, db: Database) -> None:
    reminders = await db.list_pending_reminders(message.from_user.id)
    await message.answer(
        personality.format_reminders_list(reminders, timeutils.fmt)
    )


@router.message(Command("sovet"))
async def cmd_sovet(message: Message, db: Database, ai: AIProvider) -> None:
    user = await db.get_or_create_user(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    if not get_tariff(user["tariff"]).daily_advice:
        await message.answer(personality.upsell("Совет дня"))
        return

    # собираем контекст: последние заметки + ближайшие напоминания
    notes = await db.list_notes(user["user_id"], limit=10)
    reminders = await db.list_pending_reminders(user["user_id"])
    ctx_lines = ["Последние заметки:"]
    ctx_lines += [f"- {n.get('title') or n.get('text', '')[:50]}" for n in notes] or ["(нет)"]
    ctx_lines.append("Ближайшие напоминания:")
    ctx_lines += [f"- {r['text']} ({r['remind_at']})" for r in reminders] or ["(нет)"]
    context = "\n".join(ctx_lines)

    await message.answer("Думаю над советом… 🤔")
    try:
        advice = await ai.daily_advice(context)
        await message.answer(advice)
    except AIError:
        await message.answer("Что-то ИИ задумался. Попробуй ещё разок чуть позже.")


@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database) -> None:
    user = await db.get_or_create_user(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
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


@router.message(Command("setplan"))
async def cmd_setplan(message: Message, command: CommandObject, db: Database) -> None:
    """Сменить тариф (для теста). Доступно админам или всем, если ADMIN_IDS пуст."""
    if not _is_admin(message.from_user.id):
        await message.answer("Эта команда только для админа.")
        return
    plan = (command.args or "").strip().lower()
    if plan not in VALID_TARIFFS:
        await message.answer("Укажи тариф: <code>/setplan free|pro|premium</code>")
        return
    await db.get_or_create_user(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    await db.set_tariff(message.from_user.id, plan)
    await message.answer(f"Готово. Твой тариф теперь: <b>{get_tariff(plan).title}</b> ✅")
