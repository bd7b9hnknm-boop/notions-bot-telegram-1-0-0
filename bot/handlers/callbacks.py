"""
Обработка нажатий inline-кнопок:
  save / rem / remat / remset / custom / back / cancel  — действия с черновиком;
  rdone / rsnooze                                       — реакции на сработавшее напоминание.
А также ввод «своего времени» через FSM.
"""
from __future__ import annotations

from datetime import timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ai.base import AIProvider
from ai.gemini import AIError
from bot import keyboards, pending, personality
from bot.handlers.common import create_reminder, save_note
from bot.states import ReminderFlow
from database.db import Database
from scheduler.reminders import ReminderScheduler
from utils import timeutils
from utils.logger import get_logger
from utils.tariffs import get_tariff

router = Router(name="callbacks")
logger = get_logger(__name__)

EXPIRED = "Этот черновик уже устарел 🙈 Пришли фото/сообщение заново."


def _pid(data: str) -> str:
    return data.split(":", 2)[1]


async def _finish_reminder(callback: CallbackQuery, db, scheduler, payload, when) -> None:
    """Создаём напоминание и показываем подтверждение."""
    text = payload.get("reminder_text") or payload.get("title") or "Напоминание"
    context = payload.get("note_text")
    await create_reminder(db, scheduler, callback.from_user.id, text, when, context)
    await callback.message.edit_text(
        personality.reminder_set(text, timeutils.fmt(when))
    )


# --------------------------------------------------------------- сохранить
@router.callback_query(F.data.startswith("save:"))
async def cb_save(callback: CallbackQuery, db: Database) -> None:
    payload = pending.get(_pid(callback.data))
    if not payload:
        await callback.answer(EXPIRED, show_alert=True)
        return

    note_id, code = await save_note(db, callback.from_user.id, payload)
    if code == "limit":
        user = await db.get_user(callback.from_user.id)
        limit = get_tariff(user["tariff"]).notes_limit
        await callback.message.edit_text(personality.limit_reached(limit))
        await callback.answer()
        return

    pending.pop(_pid(callback.data))
    user = await db.get_user(callback.from_user.id)
    count = await db.count_notes(callback.from_user.id)
    hint = personality.notes_left_hint(user["tariff"], count)
    await callback.message.edit_text(
        f"Сохранил в заметки (#{note_id}). 📝{hint}\n\nПосмотреть: /notes"
    )
    await callback.answer("Готово!")


# --------------------------------------------------- напомнить: выбор времени
@router.callback_query(F.data.startswith("rem:"))
async def cb_remind_menu(callback: CallbackQuery) -> None:
    pid = _pid(callback.data)
    payload = pending.get(pid)
    if not payload:
        await callback.answer(EXPIRED, show_alert=True)
        return
    deadline = timeutils.parse_deadline(payload.get("deadline"))
    options = timeutils.suggested_times(deadline)
    await callback.message.edit_text(
        "Когда напомнить? ⏰", reply_markup=keyboards.choose_time(pid, options)
    )
    await callback.answer()


# ----------------------------------------- напомнить: выбран готовый вариант
@router.callback_query(F.data.startswith("remat:"))
async def cb_remind_at(callback: CallbackQuery, db: Database,
                       scheduler: ReminderScheduler) -> None:
    _, pid, code = callback.data.split(":", 2)
    payload = pending.get(pid)
    if not payload:
        await callback.answer(EXPIRED, show_alert=True)
        return

    deadline = timeutils.parse_deadline(payload.get("deadline"))
    options = timeutils.suggested_times(deadline)
    chosen = next((o for o in options if o["code"] == code), None)
    when = chosen["dt"] if chosen else timeutils.now() + timedelta(hours=1)

    await _finish_reminder(callback, db, scheduler, payload, when)
    pending.pop(pid)
    await callback.answer("Поставил!")


# ----------------------------- напомнить: время уже понято из текста (быстро)
@router.callback_query(F.data.startswith("remset:"))
async def cb_remind_set(callback: CallbackQuery, db: Database,
                        scheduler: ReminderScheduler) -> None:
    pid = _pid(callback.data)
    payload = pending.get(pid)
    if not payload:
        await callback.answer(EXPIRED, show_alert=True)
        return
    when = timeutils.parse_deadline(payload.get("datetime"))
    if not when:
        # на всякий случай — откатываемся к меню выбора
        await cb_remind_menu(callback)
        return
    await _finish_reminder(callback, db, scheduler, payload, when)
    pending.pop(pid)
    await callback.answer("Поставил!")


# ------------------------------------------------ напомнить: своё время (FSM)
@router.callback_query(F.data.startswith("custom:"))
async def cb_custom_time(callback: CallbackQuery, state: FSMContext) -> None:
    pid = _pid(callback.data)
    if not pending.get(pid):
        await callback.answer(EXPIRED, show_alert=True)
        return
    await state.update_data(pid=pid)
    await state.set_state(ReminderFlow.waiting_custom_time)
    await callback.message.edit_text(
        "Напиши, когда напомнить 🕒\n"
        "Например: <i>завтра в 9</i>, <i>через 2 часа</i>, <i>25 числа в 18:00</i>"
    )
    await callback.answer()


@router.message(ReminderFlow.waiting_custom_time, F.text)
async def on_custom_time(message: Message, state: FSMContext, db: Database,
                         scheduler: ReminderScheduler, ai: AIProvider) -> None:
    data = await state.get_data()
    pid = data.get("pid")
    payload = pending.get(pid) if pid else None
    if not payload:
        await state.clear()
        await message.answer(EXPIRED)
        return

    # 1) быстрый разбор; 2) если не вышло — подстраховка через ИИ
    when = timeutils.parse_human(message.text)
    if not when:
        try:
            parsed = await ai.analyze_text(message.text)
            when = timeutils.parse_deadline(parsed.get("datetime"))
        except AIError:
            when = None

    if not when or when <= timeutils.now():
        await message.answer(
            "Не понял время или оно уже прошло 🤔 Попробуй так: "
            "<i>завтра в 18:00</i> или <i>через 3 часа</i>."
        )
        return

    text = payload.get("reminder_text") or payload.get("title") or "Напоминание"
    context = payload.get("note_text")
    await create_reminder(db, scheduler, message.from_user.id, text, when, context)
    pending.pop(pid)
    await state.clear()
    await message.answer(personality.reminder_set(text, timeutils.fmt(when)))


# ------------------------------------------------------------------- назад
@router.callback_query(F.data.startswith("back:"))
async def cb_back(callback: CallbackQuery) -> None:
    pid = _pid(callback.data)
    payload = pending.get(pid)
    if not payload:
        await callback.answer(EXPIRED, show_alert=True)
        return
    # возвращаем кнопки действий (текст оставляем как есть)
    label = None
    if payload.get("datetime"):
        dt = timeutils.parse_deadline(payload["datetime"])
        if dt:
            label = timeutils.fmt(dt)
    await callback.message.edit_reply_markup(
        reply_markup=keyboards.after_analysis(pid, direct_time_label=label)
    )
    await callback.answer()


# ------------------------------------------------------------------ отмена
@router.callback_query(F.data.startswith("cancel:"))
async def cb_cancel(callback: CallbackQuery) -> None:
    pending.pop(_pid(callback.data))
    await callback.message.edit_text("Окей, отменил. Если что — я рядом. 🙂")
    await callback.answer()


# ------------------------------------- реакции на сработавшее напоминание
@router.callback_query(F.data.startswith("rdone:"))
async def cb_reminder_done(callback: CallbackQuery, db: Database) -> None:
    rid = int(callback.data.split(":", 1)[1])
    await db.set_reminder_status(rid, "done")
    await callback.message.edit_text("Отлично, вычёркиваю! ✅")
    await callback.answer("Так держать!")


@router.callback_query(F.data.startswith("rsnooze:"))
async def cb_reminder_snooze(callback: CallbackQuery, db: Database,
                             scheduler: ReminderScheduler) -> None:
    rid = int(callback.data.split(":", 1)[1])
    reminder = await db.get_reminder(rid)
    if not reminder:
        await callback.answer("Напоминание не найдено.", show_alert=True)
        return
    when = timeutils.now() + timedelta(hours=1)
    await db.update_reminder_time(rid, when)
    await scheduler.schedule(rid, when)
    await callback.message.edit_text(
        f"Ок, напомню снова через час — в {timeutils.fmt(when)}. 😴"
    )
    await callback.answer()
