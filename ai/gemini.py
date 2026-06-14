"""
Провайдер Google Gemini.

Закрывает всё: анализ фото, расшифровку голосовых и разбор текста.
SDK: google-genai (новый официальный). Все вызовы — асинхронные (client.aio).

Запросы идут через пул ключей (ai/key_pool.py): при исчерпании лимита
на одном ключе бот автоматически переключается на следующий.
"""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from google.genai import errors, types

from ai import prompts
from ai.base import AIProvider
from ai.errors import AIError  # re-export: `from ai.gemini import AIError` всё ещё работает
from ai.key_pool import GeminiKeyPool
from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

__all__ = ["GeminiProvider", "AIError"]


def _today_hint() -> str:
    """Подсказка модели про текущую дату — чтобы корректно понимать «завтра» и т.п."""
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    weekdays = ["понедельник", "вторник", "среда", "четверг",
                "пятница", "суббота", "воскресенье"]
    return (f"Сегодня: {now.strftime('%Y-%m-%d %H:%M')} "
            f"({weekdays[now.weekday()]}), часовой пояс {settings.timezone}.")


def _extract_json(text: str) -> dict:
    """Достаём JSON из ответа модели, аккуратно срезая возможные ```-обёртки."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        # убираем ```json ... ```
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    # на случай мусора по краям — берём от первой { до последней }
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start:end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Не удалось разобрать JSON от модели: %s | %r", e, text[:300])
        raise AIError("Модель вернула ответ в неожиданном формате.") from e


class GeminiProvider(AIProvider):
    def __init__(self) -> None:
        self.pool = GeminiKeyPool(list(settings.gemini_api_keys))
        self.model = settings.gemini_model
        logger.info(
            "Gemini провайдер готов (модель: %s, ключей: %d)",
            self.model, len(settings.gemini_api_keys),
        )

    # ----------------------------------------------------------- низкоуровневые
    async def _generate_json(self, parts: list) -> dict:
        async def attempt(client):
            resp = await client.aio.models.generate_content(
                model=self.model,
                contents=parts,
                config=types.GenerateContentConfig(
                    system_instruction=prompts.persona(),
                    response_mime_type="application/json",
                    temperature=0.6,
                ),
            )
            return resp.text

        text = await self._run(attempt)
        return _extract_json(text)

    async def _generate_text(self, parts: list, temperature: float = 0.7) -> str:
        async def attempt(client):
            resp = await client.aio.models.generate_content(
                model=self.model,
                contents=parts,
                config=types.GenerateContentConfig(
                    system_instruction=prompts.persona(),
                    temperature=temperature,
                ),
            )
            return (resp.text or "").strip()

        return await self._run(attempt)

    async def _run(self, attempt):
        """Прогоняем запрос через пул ключей и приводим ошибки к AIError."""
        try:
            return await self.pool.run(attempt)
        except AIError:
            raise  # уже понятная ошибка (например, все ключи исчерпаны)
        except errors.APIError as e:  # битый ключ / плохой запрос и пр.
            logger.exception("Ошибка запроса к Gemini")
            raise AIError(str(e)) from e
        except Exception as e:  # сетевые и неожиданные
            logger.exception("Ошибка запроса к Gemini")
            raise AIError(str(e)) from e

    # --------------------------------------------------------------- интерфейс
    async def analyze_image(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
        parts = [
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            prompts.analyze_image_prompt() + "\n\n" + _today_hint(),
        ]
        return await self._generate_json(parts)

    async def analyze_text(self, text: str) -> dict:
        parts = [prompts.analyze_text_prompt(text) + "\n\n" + _today_hint()]
        return await self._generate_json(parts)

    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
        parts = [
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            "Расшифруй это голосовое сообщение в текст. "
            "Верни только сам текст без комментариев.",
        ]
        # для транскрипции тон не нужен, но persona не мешает
        return await self._generate_text(parts, temperature=0.2)

    async def daily_advice(self, context: str) -> str:
        parts = [prompts.daily_advice_prompt(context) + "\n\n" + _today_hint()]
        return await self._generate_text(parts)
