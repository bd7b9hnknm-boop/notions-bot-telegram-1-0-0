"""
Абстрактный интерфейс ИИ-провайдера.

Любой провайдер (Gemini, GigaChat, ...) реализует эти методы.
Благодаря этому остальной код не знает, какой именно ИИ под капотом —
провайдер переключается одной настройкой AI_PROVIDER в .env.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class AIProvider(ABC):
    @abstractmethod
    async def analyze_image(self, image_bytes: bytes, mime_type: str) -> dict:
        """Анализ фото -> словарь с разобранными полями (см. prompts.analyze_image_prompt)."""
        ...

    @abstractmethod
    async def analyze_text(self, text: str) -> dict:
        """Разбор текста/расшифровки -> словарь (см. prompts.analyze_text_prompt)."""
        ...

    @abstractmethod
    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str) -> str:
        """Голос -> текст."""
        ...

    @abstractmethod
    async def daily_advice(self, context: str) -> str:
        """Короткий совет на день (текстом)."""
        ...
