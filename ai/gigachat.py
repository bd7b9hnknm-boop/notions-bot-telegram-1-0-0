"""
Провайдер GigaChat (Сбер) — задел на будущее.

Сейчас это заглушка с понятными ошибками: структура готова, чтобы
переключиться на GigaChat одной настройкой AI_PROVIDER=gigachat, когда
будет подключён GigaChat API (анализ изображений) + Salute Speech (голос).
"""
from __future__ import annotations

from ai.base import AIProvider
from ai.gemini import AIError
from utils.logger import get_logger

logger = get_logger(__name__)

_NOT_READY = (
    "Провайдер GigaChat ещё не подключён в этой версии. "
    "Поставь AI_PROVIDER=gemini в .env."
)


class GigaChatProvider(AIProvider):
    def __init__(self) -> None:
        logger.warning("GigaChat выбран, но провайдер пока не реализован.")

    async def analyze_image(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
        raise AIError(_NOT_READY)

    async def analyze_text(self, text: str) -> dict:
        raise AIError(_NOT_READY)

    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
        raise AIError(_NOT_READY)

    async def daily_advice(self, context: str) -> str:
        raise AIError(_NOT_READY)
