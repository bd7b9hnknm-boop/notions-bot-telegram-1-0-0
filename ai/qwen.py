"""
Провайдер Qwen (Alibaba DashScope), OpenAI-совместимый API.

Эндпоинт: https://dashscope-intl.aliyuncs.com/compatible-mode/v1
Используем официальный SDK openai (AsyncOpenAI), направленный на этот base_url.

Закрывает анализ фото (Qwen-VL) и разбор текста. Голос (ASR) — отдельным
шагом: нужна конвертация ogg + аудиомодель, добавим позже.

Поддерживается несколько ключей: round-robin + переключение при лимите (429).
"""
from __future__ import annotations

import base64

from openai import APIError, AsyncOpenAI, RateLimitError

from ai import prompts
from ai.base import AIProvider
from ai.errors import AIError
from ai.parsing import extract_json, today_hint
from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class QwenProvider(AIProvider):
    def __init__(self) -> None:
        keys = list(settings.qwen_api_keys)
        if not keys:
            raise RuntimeError("Не задан ни один ключ Qwen (QWEN_API_KEYS).")
        self.clients = [
            AsyncOpenAI(api_key=k, base_url=settings.qwen_base_url) for k in keys
        ]
        self.model = settings.qwen_model
        self._idx = 0
        logger.info(
            "Qwen провайдер готов (модель: %s, ключей: %d)",
            self.model, len(self.clients),
        )

    # порядок обхода ключей (round-robin)
    def _order(self) -> list[AsyncOpenAI]:
        n = len(self.clients)
        start = self._idx % n
        self._idx = (self._idx + 1) % n
        return [self.clients[(start + i) % n] for i in range(n)]

    async def _chat(self, messages: list) -> str:
        """Вызов чата с ротацией ключей при лимите."""
        last_err: Exception | None = None
        for client in self._order():
            try:
                resp = await client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.6,
                )
                return resp.choices[0].message.content or ""
            except RateLimitError as e:           # 429 — пробуем следующий ключ
                logger.warning("Qwen: ключ упёрся в лимит (429), переключаюсь.")
                last_err = e
                continue
            except APIError as e:                 # auth / битый запрос / сеть
                logger.exception("Qwen API error")
                raise AIError(str(e)) from e
        raise AIError("Все ключи Qwen временно исчерпали лимит. Попробуй позже. 🙏")

    # --------------------------------------------------------------- интерфейс
    async def analyze_image(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        messages = [
            {"role": "system", "content": prompts.persona()},
            {"role": "user", "content": [
                {"type": "text",
                 "text": prompts.analyze_image_prompt() + "\n\n" + today_hint()},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
            ]},
        ]
        return extract_json(await self._chat(messages))

    async def analyze_text(self, text: str) -> dict:
        messages = [
            {"role": "system", "content": prompts.persona()},
            {"role": "user",
             "content": prompts.analyze_text_prompt(text) + "\n\n" + today_hint()},
        ]
        return extract_json(await self._chat(messages))

    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
        # ASR для Qwen добавим следующим шагом (нужна конвертация ogg + аудиомодель)
        raise AIError("Распознавание голоса на Qwen ещё в разработке — пришли текстом 🙏")

    async def daily_advice(self, context: str) -> str:
        messages = [
            {"role": "system", "content": prompts.persona()},
            {"role": "user",
             "content": prompts.daily_advice_prompt(context) + "\n\n" + today_hint()},
        ]
        return (await self._chat(messages)).strip()
