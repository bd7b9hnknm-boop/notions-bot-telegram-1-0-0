"""
Обработка нажатий кнопок.

Группы:
  draft (разбор): save / rem / remset / done / cancel
  время (единое):  tset / tcustom / tback  (target = d_<pid> | r_<rid>)
  заметки:         note / nlist / nrem / ndel / ndelyes
  напоминания:     rmanage / rdone / rack / rcancel / rresched / rlist
                   rsnooze / rsnoozeat / fired-кнопки
  меню:            menu:*
"""
from __future__ import annotations

from datetime import timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ai.base import AIProvider
from ai.gemini import AIError
from bot import keyboards, pending, personality, views
from bot.handlers.common import create_reminder, save_note
from bot.states import ReminderFlow
from database.db import Database
from scheduler.reminders import ReminderScheduler
from utils import timeutils
from utils.logger import get_logger
from utils.tariffs import get_tariff

router = Router(name="callbacks")
logger = get_logger(__name__)


def _id(data: str) -> str:
    return data.split(":", 2)[1]


def _resolve_code(code: str, deadline) -> "timeutils.datetime":
    opts = timeutils.suggested_times(deadline)
    o = next((x for x in opts if x["code"] == code), None)
    return o["dt"] if o else timeutils.now() + timedelta(hours=1)


def _resolve_snooze(code: str):
    n = timeutils.now()
    if code == "m10":
        return n + timedelta(minutes=10)
    if code == "h1":
        return n + timedelta(hours=1)
    if code == "h3":
        return n + timedelta(hours=3)
    if code == "eve":
        eve = n.replace(hour=19, minute=0, second=0, microsecond=0)
        return eve if eve > n else eve + timedelta(days=1)
    if code == "morn":
        return (n + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    return n + timedelta(hours=1)


# ============================================================ draft: сохранить
@router.callback_query(F.data.startswith("save:"))
async def cb_save(callback: CallbackQuery, db: Database) -> None:
    pid = _id(callback.data)
    payload = pending.get(pid)
    if not payload:
        await callback.answer(personality.expired(), show_alert=True)
        return

    note_id, code = await save_note(db, callback.from_user.id, payload)
    if code == "limit":
        user = await db.get_user(callback.from_user.id)
        await callback.message.edit_text(
            personality.limit_reached(get_tariff(user["tariff"]).notes_limit)
        )
        await callback.answer()
        return

    payload["saved"] = note_id
    await callback.message.edit_text(
        personality.render_card(payload),
        reply_markup=keyboards.after_analysis(pid, payload, _direct_label(payload)),
    )
    await callback.answer(personality.saved_note(note_id))


def _direct_label(payload: dict) -> str | None:
    """Подпись кнопки быстрого подтверждения времени (если ИИ понял время)."""
    dt = timeutils.parse_deadline(payload.get("datetime"))
    if dt and dt > timeutils.now():
        return timeutils.describe_schedule(payload.get("repeat") or "none", dt)
    return None


# ============================================================ draft: напомнить
@router.callback_query(F.data.startswith("rem:"))
async def cb_remind_menu(callback: CallbackQuery) -> None:
    pid = _id(callback.data)
    payload = pending.get(pid)
    if not payload:
        await callback.answer(personality.expired(), show_alert=True)
        return
    deadline = timeutils.parse_deadline(payload.get("deadline"))
    options = timeutils.suggested_times(deadline)
    await callback.message.edit_text(
        "Когда напомнить? ⏰", reply_markup=keyboards.choose_time(f"d_{pid}", options)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("remset:"))
async def cb_remind_set(callback: CallbackQuery, db: Database,
                        scheduler: ReminderScheduler) -> None:
    pid = _id(callback.data)
    payload = pending.get(pid)
    if not payload:
        await callback.answer(personality.expired(), show_alert=True)
        return
    dt = timeutils.parse_deadline(payload.get("datetime"))
    if not dt:
        await cb_remind_menu(callback)
        return
    repeat = payload.get("repeat") or "none"
    await _commit_draft_reminder(callback, db, scheduler, pid, dt, repeat)
    await callback.answer("Поставил!")


async def _commit_draft_reminder(callback, db, scheduler, pid, dt, repeat) -> None:
    payload = pending.get(pid)
    text = payload.get("reminder_text") or payload.get("title") or "Напоминание"
    context = payload.get("note_text")
    await create_reminder(db, scheduler, callback.from_user.id, text, dt, context, repeat)
    payload["reminded"] = timeutils.describe_schedule(repeat, dt)
    await callback.message.edit_text(
        personality.render_card(payload),
        reply_markup=keyboards.after_analysis(pid, payload, _direct_label(payload)),
    )


# ============================================================ draft: финал
@router.callback_query(F.data.startswith("done:"))
async def cb_done(callback: CallbackQuery) -> None:
    pid = _id(callback.data)
    payload = pending.pop(pid)
    if payload:
        await callback.message.edit_text(personality.render_card(payload))
    await callback.answer("Готово 👌")


@router.callback_query(F.data.startswith("cancel:"))
async def cb_cancel(callback: CallbackQuery) -> None:
    pending.pop(_id(callback.data))
    await callback.message.edit_text(personality.cancelled())
    await callback.answer()


# ============================================================ единое время
@router.callback_query(F.data.startswith("tset:"))
async def cb_time_set(callback: CallbackQuery, db: Database,
                      scheduler: ReminderScheduler) -> None:
    _, target, code = callback.data.split(":", 2)
    kind, ident = target[0], target[2:]

    if kind == "d":  # черновик
        payload = pending.get(ident)
        if not payload:
            await callback.answer(personality.expired(), show_alert=True)
            return
        deadline = timeutils.parse_deadline(payload.get("deadline"))
        dt = _resolve_code(code, deadline)
        await _commit_draft_reminder(callback, db, scheduler, ident, dt, "none")
        await callback.answer("Поставил!")
    else:  # перенос существующего напоминания
        rid = int(ident)
        dt = _resolve_code(code, None)
        await db.update_reminder_time(rid, dt)
        await scheduler.schedule(rid)
        await _show_reminder_card(callback, db, rid, note="Перенёс ✅")
        await callback.answer("Перенёс!")


@router.callback_query(F.data.startswith("tcustom:"))
async def cb_time_custom(callback: CallbackQuery, state: FSMContext) -> None:
    target = _id(callback.data)
    await state.update_data(
        target=target,
        prompt_chat=callback.message.chat.id,
        prompt_msg=callback.message.message_id,
    )
    await state.set_state(ReminderFlow.waiting_custom_time)
    await callback.message.edit_text(
        "Напиши, когда напомнить 🕒\n"
        "Например: <i>завтра в 9</i>, <i>через 2 часа</i>, <i>каждый день в 8</i>"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tback:"))
async def cb_time_back(callback: CallbackQuery, db: Database) -> None:
    target = _id(callback.data)
    kind, ident = target[0], target[2:]
    if kind == "d":
        payload = pending.get(ident)
        if not payload:
            await callback.answer(personality.expired(), show_alert=True)
            return
        await callback.message.edit_text(
            personality.render_card(payload),
            reply_markup=keyboards.after_analysis(ident, payload, _direct_label(payload)),
        )
    else:
        await _show_reminder_card(callback, db, int(ident))
    await callback.answer()


@router.message(ReminderFlow.waiting_custom_time, F.text)
async def on_custom_time(message: Message, state: FSMContext, db: Database,
                         scheduler: ReminderScheduler, ai: AIProvider) -> None:
    data = await state.get_data()
    target = data.get("target", "")
    kind, ident = (target[0], target[2:]) if target else ("", "")

    when = timeutils.parse_human(message.text)
    if not when:
        try:
            parsed = await ai.analyze_text(message.text)
            when = timeutils.parse_deadline(parsed.get("datetime"))
        except AIError:
            when = None
    if not when or when <= timeutils.now():
        await message.answer(
            "Не понял время или оно уже прошло 🤔 Попробуй: "
            "<i>завтра в 18:00</i> или <i>через 3 часа</i>."
        )
        return

    await state.clear()
    chat = data.get("prompt_chat")
    msg = data.get("prompt_msg")

    if kind == "d":
        payload = pending.get(ident)
        if not payload:
            await message.answer(personality.expired())
            return
        text = payload.get("reminder_text") or payload.get("title") or "Напоминание"
        await create_reminder(db, scheduler, message.from_user.id, text, when,
                              payload.get("note_text"), "none")
        payload["reminded"] = timeutils.fmt(when)
        try:
            await message.bot.edit_message_text(
                personality.render_card(payload), chat_id=chat, message_id=msg,
                reply_markup=keyboards.after_analysis(ident, payload, _direct_label(payload)),
            )
        except Exception:
            await message.answer(personality.reminder_set(text, timeutils.fmt(when)))
    else:
        rid = int(ident)
        await db.update_reminder_time(rid, when)
        await scheduler.schedule(rid)
        await message.answer(personality.snooze_set(timeutils.fmt(when)))


# ============================================================ заметки
@router.callback_query(F.data.startswith("note:"))
async def cb_note_open(callback: CallbackQuery, db: Database) -> None:
    note = await db.get_note(int(_id(callback.data)), callback.from_user.id)
    if not note:
        await callback.answer("Заметку не нашёл 🤷", show_alert=True)
        return
    await callback.message.edit_text(
        personality.note_card(note), reply_markup=keyboards.note_manage(note["id"])
    )
    await callback.answer()


@router.callback_query(F.data == "nlist")
async def cb_notes_back(callback: CallbackQuery, db: Database) -> None:
    text, kb = await views.notes_view(db, callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("nrem:"))
async def cb_note_remind(callback: CallbackQuery, db: Database) -> None:
    note = await db.get_note(int(_id(callback.data)), callback.from_user.id)
    if not note:
        await callback.answer("Заметку не нашёл 🤷", show_alert=True)
        return
    title = note.get("title") or (note.get("text") or "Заметка")[:60]
    payload = {
        "reminder_text": title,
        "note_text": note.get("text"),
        "title": title,
        "deadline": None,
        "datetime": None,
        "repeat": "none",
        "display": f"⏰ Напоминание по заметке:\n📝 <b>{personality.e(title)}</b>",
        "saved": note["id"],
        "reminded": None,
    }
    pid = pending.put(payload)
    options = timeutils.suggested_times(None)
    await callback.message.edit_text(
        "Когда напомнить об этой заметке? ⏰",
        reply_markup=keyboards.choose_time(f"d_{pid}", options),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ndelyes:"))
async def cb_note_delete_yes(callback: CallbackQuery, db: Database) -> None:
    note_id = int(_id(callback.data))
    await db.delete_note(note_id, callback.from_user.id)
    await callback.message.edit_text(personality.note_deleted())
    await callback.answer()


@router.callback_query(F.data.startswith("ndel:"))
async def cb_note_delete(callback: CallbackQuery) -> None:
    note_id = int(_id(callback.data))
    await callback.message.edit_text(
        "Точно удалить эту заметку?",
        reply_markup=keyboards.confirm_delete(note_id),
    )
    await callback.answer()


# ============================================================ напоминания
async def _show_reminder_card(callback: CallbackQuery, db: Database, rid: int,
                              note: str | None = None) -> None:
    r = await db.get_reminder(rid)
    if not r or r["status"] != "pending":
        await callback.message.edit_text("Этого напоминания уже нет. 🤷")
        return
    recurring = (r.get("repeat") or "none") != "none"
    text = personality.reminder_card(r)
    if note:
        text = f"{note}\n\n{text}"
    await callback.message.edit_text(
        text, reply_markup=keyboards.reminder_manage(rid, recurring)
    )


@router.callback_query(F.data.startswith("rmanage:"))
async def cb_reminder_manage(callback: CallbackQuery, db: Database) -> None:
    await _show_reminder_card(callback, db, int(_id(callback.data)))
    await callback.answer()


@router.callback_query(F.data == "rlist")
async def cb_reminders_back(callback: CallbackQuery, db: Database) -> None:
    text, kb = await views.reminders_view(db, callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("rdone:"))
async def cb_reminder_done(callback: CallbackQuery, db: Database,
                           scheduler: ReminderScheduler) -> None:
    rid = int(_id(callback.data))
    await db.set_reminder_status(rid, "done")
    await scheduler.cancel(rid)
    await callback.message.edit_text(personality.reminder_done())
    await callback.answer("Так держать!")


@router.callback_query(F.data.startswith("rack:"))
async def cb_reminder_ack(callback: CallbackQuery) -> None:
    # повторяющееся — просто подтверждаем, расписание остаётся
    await callback.message.edit_text("👍 Принято, напомню в следующий раз.")
    await callback.answer()


@router.callback_query(F.data.startswith("rcancel:"))
async def cb_reminder_cancel(callback: CallbackQuery, db: Database,
                             scheduler: ReminderScheduler) -> None:
    rid = int(_id(callback.data))
    await db.set_reminder_status(rid, "cancelled")
    await scheduler.cancel(rid)
    await callback.message.edit_text(personality.reminder_cancelled())
    await callback.answer()


@router.callback_query(F.data.startswith("rresched:"))
async def cb_reminder_resched(callback: CallbackQuery) -> None:
    rid = int(_id(callback.data))
    options = timeutils.suggested_times(None)
    await callback.message.edit_text(
        "На какое время перенести? 🕒",
        reply_markup=keyboards.choose_time(f"r_{rid}", options),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rsnoozeat:"))
async def cb_snooze_at(callback: CallbackQuery, db: Database,
                       scheduler: ReminderScheduler) -> None:
    _, rid_s, code = callback.data.split(":", 2)
    rid = int(rid_s)
    when = _resolve_snooze(code)
    await db.update_reminder_time(rid, when)
    await scheduler.schedule(rid)
    await callback.message.edit_text(personality.snooze_set(timeutils.fmt(when)))
    await callback.answer()


@router.callback_query(F.data.startswith("rsnooze:"))
async def cb_snooze_menu(callback: CallbackQuery) -> None:
    rid = int(_id(callback.data))
    await callback.message.edit_text(
        "На сколько отложить? 😴", reply_markup=keyboards.snooze_menu(rid)
    )
    await callback.answer()


# ============================================================ меню
@router.callback_query(F.data.startswith("menu:"))
async def cb_menu(callback: CallbackQuery, db: Database, ai: AIProvider) -> None:
    what = _id(callback.data)
    uid = callback.from_user.id
    if what == "today":
        text, kb = await views.today_view(db, uid)
    elif what == "notes":
        text, kb = await views.notes_view(db, uid)
    elif what == "reminders":
        text, kb = await views.reminders_view(db, uid)
    elif what == "upgrade":
        user = await db.get_or_create_user(uid, callback.from_user.username,
                                           callback.from_user.first_name)
        text, kb = views.upgrade_view(user["tariff"])
    elif what == "help":
        text, kb = personality.help_text(), None
    elif what == "sovet":
        user = await db.get_or_create_user(uid, callback.from_user.username,
                                           callback.from_user.first_name)
        await callback.answer()
        await callback.message.answer(await views.sovet_view(db, ai, user))
        return
    else:
        text, kb = personality.menu_text(), keyboards.main_menu_inline()
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()
