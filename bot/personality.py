"""
Тексты и форматирование сообщений в характере бота.

Всё, что видит пользователь (приветствия, оформление результатов,
апселл тарифов), собрано здесь. Динамические данные экранируем для HTML.
"""
from __future__ import annotations

from html import escape

from config import settings
from utils.tariffs import TARIFFS, FREE, PRO, PREMIUM, get_tariff, notes_left

NAME = settings.bot_name


def e(text: object) -> str:
    """Экранируем произвольный текст для HTML-разметки Telegram."""
    return escape(str(text)) if text is not None else ""


# --------------------------------------------------------------- приветствия
def greeting(first_name: str | None) -> str:
    who = e(first_name) if first_name else "друг"
    return (
        f"Привет, {who}! Я <b>{e(NAME)}</b> — твой ассистент по заметкам и напоминаниям. 🗒️\n\n"
        "Кидай мне что угодно:\n"
        "📷 <b>Фото</b> — квитанцию, доску с задачами, список покупок, расписание. "
        "Я разберу и предложу, что с этим сделать.\n"
        "🎤 <b>Голосовое</b> — наговори мысль, я расшифрую и сохраню.\n"
        "✍️ <b>Текст</b> — «напомни завтра в 18:00 позвонить маме» — пойму и поставлю напоминание.\n\n"
        "Команды: /notes — заметки · /reminders — напоминания · /help — справка"
    )


def help_text() -> str:
    return (
        f"<b>Что я умею</b> 🤔\n\n"
        "📷 <b>Фото</b> → анализирую и предлагаю заметку или напоминание.\n"
        "🎤 <b>Голос</b> → расшифровываю в текст и разбираю.\n"
        "✍️ <b>Текст</b> → понимаю, заметка это или напоминание со временем.\n\n"
        "<b>Команды</b>\n"
        "/notes — последние заметки\n"
        "/find &lt;слово&gt; — поиск по заметкам\n"
        "/reminders — активные напоминания\n"
        "/sovet — совет на день (PRO)\n"
        "/stats — аналитика (PRO)\n"
        "/upgrade — тарифы\n\n"
        "Подсказка: я дотошный к дедлайнам — если в фото есть срок, "
        "сам предложу напомнить заранее. 😉"
    )


def thinking(kind: str = "фото") -> str:
    return f"Секунду, смотрю {e(kind)}… 🔍"


# ---------------------------------------------------------- разбор/результат
def format_analysis(data: dict) -> str:
    """Красивый вывод результата анализа фото."""
    reply = data.get("reply")
    lines: list[str] = []

    if reply:
        lines.append(e(reply))
        lines.append("")

    title = data.get("title")
    if title:
        lines.append(f"📌 <b>{e(title)}</b>")

    type_ = data.get("type")
    category = data.get("category")
    meta = " · ".join(filter(None, [e(type_) if type_ else "", e(category) if category else ""]))
    if meta:
        lines.append(f"🏷 <i>{meta}</i>")

    key_info = data.get("key_info") or []
    if key_info:
        lines.append("")
        for item in key_info:
            lines.append(f"• {e(item)}")

    deadline = data.get("deadline")
    if deadline and str(deadline).lower() not in {"null", "none"}:
        lines.append(f"\n⏳ <b>Срок:</b> {e(deadline)}")

    return "\n".join(lines).strip() or "Готово."


def format_text_intent(data: dict) -> str:
    """Вывод результата разбора текста/голоса."""
    reply = data.get("reply")
    text = data.get("text")
    lines: list[str] = []
    if reply:
        lines.append(e(reply))
    if text and text != reply:
        lines.append(f"\n«{e(text)}»")
    return "\n".join(lines).strip() or "Принял."


# ------------------------------------------------------------------- заметки
def format_notes_list(notes: list[dict]) -> str:
    if not notes:
        return ("Заметок пока нет. Пришли мне фото, голосовое или текст — "
                "и первая появится. ✨")
    lines = ["<b>Твои последние заметки</b> 🗂️\n"]
    for n in notes:
        cat = f" · <i>{e(n['category'])}</i>" if n.get("category") else ""
        title = n.get("title") or (n.get("text") or "")[:40]
        lines.append(f"#{n['id']} 📝 <b>{e(title)}</b>{cat}")
    lines.append("\nУдалить: /del &lt;номер&gt;")
    return "\n".join(lines)


def format_search_results(query: str, notes: list[dict]) -> str:
    if not notes:
        return f"По запросу «{e(query)}» ничего не нашёл. 🤷"
    lines = [f"<b>Нашёл по «{e(query)}»:</b>\n"]
    for n in notes:
        title = n.get("title") or (n.get("text") or "")[:40]
        lines.append(f"#{n['id']} 📝 {e(title)}")
    return "\n".join(lines)


# --------------------------------------------------------------- напоминания
def format_reminders_list(reminders: list[dict], fmt_time) -> str:
    from datetime import datetime
    if not reminders:
        return "Активных напоминаний нет. Спокойно. 😌"
    lines = ["<b>Активные напоминания</b> ⏰\n"]
    for r in reminders:
        try:
            dt = datetime.fromisoformat(r["remind_at"])
            when = fmt_time(dt)
        except Exception:
            when = r["remind_at"]
        lines.append(f"#{r['id']} • {e(r['text'])}\n   🕒 {e(when)}")
    return "\n".join(lines)


def reminder_set(text: str, when_str: str) -> str:
    return (f"Готово! Напомню: <b>{e(text)}</b>\n"
            f"🕒 {e(when_str)}\n\nНе переживай, не забуду. 🙂")


def reminder_fired(text: str, context: str | None) -> str:
    base = f"⏰ <b>Напоминание!</b>\n\n{e(text)}"
    if context:
        base += f"\n\n<i>{e(context)}</i>"
    return base


# ------------------------------------------------------------------- тарифы
def upgrade_text(current: str) -> str:
    cur = get_tariff(current)
    lines = [f"Твой тариф сейчас: <b>{cur.title}</b>\n"]
    lines.append(
        "<b>FREE</b> — бесплатно\n"
        f"✅ {TARIFFS[FREE].notes_limit} заметок\n"
        "✅ Анализ фото\n"
        "✅ Голосовые и напоминания\n"
    )
    lines.append(
        "<b>PRO</b> — 99 ₽/мес\n"
        "✨ Безлимит заметок\n"
        "✨ Умные советы каждый день\n"
        "✨ Аналитика продуктивности\n"
        "✨ Экспорт в Notion/Google Calendar\n"
    )
    lines.append(
        "<b>PREMIUM</b> — 299 ₽/мес\n"
        "🔥 Всё из PRO\n"
        "🔥 Приоритет в обработке фото\n"
        "🔥 Персональные фишки под твои привычки\n"
        "🔥 Семейный доступ (до 5 человек)\n"
    )
    lines.append("Оплата скоро появится прямо здесь. 💳")
    return "\n".join(lines)


def upsell(feature: str) -> str:
    """Дружелюбный апселл, когда фича недоступна на FREE."""
    return (f"{e(feature)} — это фишка тарифа <b>PRO</b>. ✨\n"
            "Посмотреть, что даёт PRO: /upgrade")


def limit_reached(limit: int) -> str:
    return (f"Упёрлись в лимит — {limit} заметок на бесплатном тарифе. 📦\n"
            "На <b>PRO</b> заметки безлимитные: /upgrade\n"
            "Или удали ненужные: /notes → /del &lt;номер&gt;")


def notes_left_hint(tariff: str, count: int) -> str:
    left = notes_left(tariff, count)
    if left is None:
        return ""
    if left <= 5:
        return f"\n\n<i>Осталось {left} заметок на FREE.</i>"
    return ""
