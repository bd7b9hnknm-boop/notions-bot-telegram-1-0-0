"""
Тексты и форматирование сообщений в характере бота.

Характер: спокойный и внимательный к деталям/дедлайнам, но бодро подгоняет,
когда дело срочное. Говорит по-человечески, на «ты», без канцелярита.

Чтобы не звучать как робот, ключевые реплики берём из наборов вариантов
(pick) — каждый раз чуть по-разному.
"""
from __future__ import annotations

import random
from datetime import datetime
from html import escape

from config import settings
from utils import timeutils
from utils.tariffs import TARIFFS, FREE, PRO, PREMIUM, get_tariff, notes_left

NAME = settings.bot_name


def e(text: object) -> str:
    """Экранируем произвольный текст для HTML-разметки Telegram."""
    return escape(str(text)) if text is not None else ""


def pick(options: list[str]) -> str:
    return random.choice(options)


# ============================================================ приветствие
def greeting(first_name: str | None) -> str:
    who = e(first_name) if first_name else "друг"
    hello = pick([f"Привет, {who}!", f"О, привет, {who}!", f"На связи, {who}!"])
    return (
        f"{hello} Я <b>{e(NAME)}</b> — твой ассистент по заметкам и напоминаниям. 🗒️\n\n"
        "Я не просто храню — я <i>думаю</i>. Кидай что угодно, разберусь и предложу, "
        "что с этим сделать:\n\n"
        "📷 <b>Фото</b> — квитанция, доска задач, список покупок, расписание.\n"
        "🎤 <b>Голосовое</b> — наговори мысль, я расшифрую.\n"
        "✍️ <b>Текст</b> — «напомни завтра в 18:00 позвонить маме» — пойму и поставлю.\n\n"
        "💡 Понимаю и повторы: <i>«каждый день в 9 выпить воды»</i>.\n\n"
        "Нажми <b>«📅 Сегодня»</b> внизу или просто пришли мне что-нибудь. Поехали! 🚀"
    )


def help_text() -> str:
    return (
        "<b>Что я умею</b> 🤔\n\n"
        "📷 <b>Фото</b> → разбираю и предлагаю заметку или напоминание.\n"
        "🎤 <b>Голос</b> → расшифровываю и понимаю.\n"
        "✍️ <b>Текст</b> → заметка это или напоминание со временем (и повтором).\n\n"
        "<b>Команды</b>\n"
        "/today — что на сегодня 📅\n"
        "/notes — заметки 📝\n"
        "/find &lt;слово&gt; — поиск\n"
        "/reminders — напоминания ⏰\n"
        "/sovet — совет дня (PRO)\n"
        "/stats — аналитика (PRO)\n"
        "/menu — меню · /upgrade — тарифы\n\n"
        "Подсказка: я дотошный к срокам — если в фото есть дедлайн, сам предложу "
        "напомнить заранее. 😉"
    )


def menu_text() -> str:
    return pick([
        "Чем займёмся? 👇",
        "Что показать? 👇",
        "Выбирай 👇",
    ])


# ============================================================ «думаю…»
def thinking(kind: str = "фото") -> str:
    pools = {
        "фото": ["Секунду, рассматриваю… 🔍", "Так, что тут у нас… 🔍",
                 "Вглядываюсь в фото… 🔍"],
        "голосовое": ["Слушаю… 🎧", "Секунду, расшифровываю… 🎧"],
        "сообщение": ["Минутку, вникаю… 🤔", "Так, читаю… 🤔", "Секунду… 🤔"],
    }
    return pick(pools.get(kind, ["Секунду… 🔍"]))


# ============================================================ разбор / карточка
def format_analysis(data: dict) -> str:
    """Тело разбора фото (без статуса действий — он добавляется отдельно)."""
    lines: list[str] = []
    if data.get("reply"):
        lines.append(e(data["reply"]))
        lines.append("")

    if data.get("title"):
        lines.append(f"📌 <b>{e(data['title'])}</b>")

    meta = " · ".join(filter(None, [
        e(data.get("type")) if data.get("type") else "",
        e(data.get("category")) if data.get("category") else "",
    ]))
    if meta:
        lines.append(f"🏷 <i>{meta}</i>")

    for item in (data.get("key_info") or []):
        lines.append(f"• {e(item)}")

    deadline = data.get("deadline")
    if deadline and str(deadline).lower() not in {"null", "none"}:
        lines.append(f"\n⏳ <b>Срок:</b> {e(deadline)}")

    return "\n".join(lines).strip() or "Готово."


def format_text_intent(data: dict) -> str:
    lines: list[str] = []
    if data.get("reply"):
        lines.append(e(data["reply"]))
    text = data.get("text")
    if text and text != data.get("reply"):
        lines.append(f"\n«{e(text)}»")
    return "\n".join(lines).strip() or "Принял."


def render_card(payload: dict) -> str:
    """Карточка разбора + статус уже сделанных действий (для перерисовки)."""
    parts = [payload.get("display") or "Готово."]
    status: list[str] = []
    if payload.get("saved"):
        status.append(f"✅ В заметках <b>#{payload['saved']}</b>")
    if payload.get("reminded"):
        status.append(f"⏰ Напомню: <b>{e(payload['reminded'])}</b>")
    if status:
        parts.append("\n" + "\n".join(status))
    return "\n".join(parts).strip()


# ============================================================ заметки
def format_notes_list(notes: list[dict]) -> str:
    if not notes:
        return pick([
            "Заметок пока нет. Пришли фото, голосовое или текст — и появится первая. ✨",
            "Тут пусто. Кинь мне что-нибудь — заведём первую заметку. ✨",
        ])
    lines = ["<b>Твои заметки</b> 🗂️\n", "Нажми на любую, чтобы открыть:"]
    return "\n".join(lines)


def note_card(note: dict) -> str:
    """Полная карточка одной заметки."""
    title = note.get("title") or "Заметка"
    lines = [f"📝 <b>{e(title)}</b>"]

    meta_bits = []
    if note.get("category"):
        meta_bits.append(e(note["category"]))
    try:
        d = datetime.fromisoformat(note["created_at"])
        meta_bits.append(d.strftime("%d.%m.%Y"))
    except Exception:
        pass
    if meta_bits:
        lines.append(f"🏷 <i>{' · '.join(meta_bits)}</i>")

    if note.get("text"):
        lines.append(f"\n{e(note['text'])}")

    if note.get("tags"):
        tags = " ".join(f"#{e(t.strip())}" for t in str(note["tags"]).split(",") if t.strip())
        if tags:
            lines.append(f"\n{tags}")
    return "\n".join(lines)


def format_search_results(query: str, notes: list[dict]) -> str:
    if not notes:
        return pick([
            f"По запросу «{e(query)}» ничего не нашёл. 🤷",
            f"Хм, «{e(query)}» — пусто. Попробуй другое слово. 🤷",
        ])
    return f"<b>Нашёл по «{e(query)}»</b> — нажми, чтобы открыть:"


def note_deleted() -> str:
    return pick(["Удалил. 🗑️", "Готово, выкинул. 🗑️", "Нет так нет — удалил. 🗑️"])


def limit_reached(limit: int) -> str:
    return (f"Упёрлись в лимит — {limit} заметок на бесплатном тарифе. 📦\n"
            "На <b>PRO</b> заметки безлимитные: /upgrade\n"
            "Или загляни в /notes и удали ненужное.")


def notes_left_hint(tariff: str, count: int) -> str:
    left = notes_left(tariff, count)
    if left is None:
        return ""
    if left <= 5:
        return f"\n\n<i>Осталось {left} заметок на FREE.</i>"
    return ""


# ============================================================ напоминания
def reminder_set(text: str, schedule_desc: str, recurring: bool = False) -> str:
    tail = pick(["Не переживай, не забуду. 🙂", "Я прослежу. 🙂", "Держу в голове. 🙂"])
    head = "Готово, буду напоминать! 🔁" if recurring else pick(
        ["Готово! ✅", "Принято! ✅", "Поставил! ✅"])
    return f"{head}\n<b>{e(text)}</b>\n🕒 {e(schedule_desc)}\n\n{tail}"


def format_reminders_list(reminders: list[dict]) -> str:
    if not reminders:
        return pick([
            "Активных напоминаний нет. Спокойно. 😌",
            "Пусто — ничего не висит. Дыши ровно. 😌",
        ])
    lines = ["<b>Активные напоминания</b> ⏰\n", "Нажми, чтобы управлять:"]
    return "\n".join(lines)


def reminder_line(r: dict) -> str:
    """Короткая строка-подпись для кнопки/списка напоминания."""
    try:
        dt = datetime.fromisoformat(r["remind_at"])
        when = timeutils.describe_schedule(r.get("repeat") or "none", dt)
    except Exception:
        when = r.get("remind_at", "")
    icon = "🔁" if (r.get("repeat") or "none") != "none" else "⏰"
    text = (r.get("text") or "")[:40]
    return f"{icon} {text} — {when}"


def reminder_card(r: dict) -> str:
    try:
        dt = datetime.fromisoformat(r["remind_at"])
        when = timeutils.describe_schedule(r.get("repeat") or "none", dt)
    except Exception:
        when = r.get("remind_at", "")
    icon = "🔁" if (r.get("repeat") or "none") != "none" else "⏰"
    lines = [f"{icon} <b>{e(r.get('text'))}</b>", f"🕒 {e(when)}"]
    if r.get("context"):
        lines.append(f"\n<i>{e(r['context'])}</i>")
    return "\n".join(lines)


def reminder_fired(text: str, context: str | None, repeat: str = "none") -> str:
    head = pick(["⏰ <b>Напоминание!</b>", "⏰ <b>Эй, не забудь!</b>", "⏰ <b>Пора!</b>"])
    base = f"{head}\n\n{e(text)}"
    if context:
        base += f"\n\n<i>{e(context)}</i>"
    return base


def reminder_done() -> str:
    return pick(["Отлично, вычёркиваю! ✅", "Так держать! ✅", "Есть! Одним делом меньше. ✅",
                 "Красава, сделано! ✅"])


def reminder_cancelled() -> str:
    return pick(["Отменил напоминание. 🚫", "Убрал, больше не напомню. 🚫"])


def snooze_set(schedule_desc: str) -> str:
    return pick([
        f"Ок, вернусь к этому — {schedule_desc}. 😴",
        f"Отложил. Напомню {schedule_desc}. 😴",
    ])


# ============================================================ агенда дня
def today_text(one_off: list[dict], recurring: list[dict], notes_today: int) -> str:
    today = timeutils.now().strftime("%d.%m")
    lines = [f"<b>Сегодня, {today}</b> 📅\n"]

    if not one_off and not recurring:
        lines.append(pick([
            "На сегодня напоминаний нет. Можно выдохнуть. 😌",
            "Сегодня чисто — никаких дедлайнов. 😌",
        ]))
    else:
        if one_off:
            lines.append("⏰ <b>Разовые:</b>")
            for r in sorted(one_off, key=lambda x: x["remind_at"]):
                try:
                    t = datetime.fromisoformat(r["remind_at"]).strftime("%H:%M")
                except Exception:
                    t = "—"
                lines.append(f"  {t} — {e(r.get('text'))}")
        if recurring:
            lines.append("\n🔁 <b>Регулярные:</b>")
            for r in recurring:
                try:
                    dt = datetime.fromisoformat(r["remind_at"])
                    lines.append(f"  {dt.strftime('%H:%M')} — {e(r.get('text'))}")
                except Exception:
                    lines.append(f"  {e(r.get('text'))}")

    if notes_today:
        lines.append(f"\n📝 Заметок за сегодня: <b>{notes_today}</b>")
    return "\n".join(lines)


# ============================================================ тарифы
def upgrade_text(current: str) -> str:
    cur = get_tariff(current)
    return "\n".join([
        f"Твой тариф: <b>{cur.title}</b>\n",
        "<b>FREE</b> — бесплатно",
        f"✅ {TARIFFS[FREE].notes_limit} заметок · анализ фото · голос · напоминания\n",
        "<b>PRO</b> — 99 ₽/мес",
        "✨ Безлимит заметок · совет дня · аналитика · экспорт в Notion/Calendar\n",
        "<b>PREMIUM</b> — 299 ₽/мес",
        "🔥 Всё из PRO · приоритет фото · персональные фишки · семейный доступ (5)\n",
        "Оплата скоро появится прямо здесь. 💳",
    ])


def upsell(feature: str) -> str:
    return (f"{e(feature)} — это фишка тарифа <b>PRO</b>. ✨\n"
            "Что даёт PRO: /upgrade")


# ============================================================ фоллбэк
def unsupported(kind: str) -> str:
    base = {
        "document": "Файлы я пока не разбираю 🙈",
        "sticker": "Стикеры милые, но смысла в них не считываю 🙂",
        "video": "Видео не осилю 🙈",
        "other": "Хм, такое я пока не понимаю 🙈",
    }.get(kind, "Хм, такое я пока не понимаю 🙈")
    return (f"{base}\nПришли мне <b>фото</b> 📷, <b>голосовое</b> 🎤 или "
            "<b>текст</b> ✍️ — вот это я разберу!")


def cancelled() -> str:
    return pick(["Окей, отменил. Если что — я рядом. 🙂", "Понял, забыли. Я тут. 🙂"])


def expired() -> str:
    return "Этот черновик уже устарел 🙈 Пришли фото/сообщение заново."


def saved_note(note_id: int) -> str:
    return pick([f"Сохранил в заметки (#{note_id}). 📝",
                 f"Записал (#{note_id}). 📝", f"Готово, в заметках #{note_id}. 📝"])
