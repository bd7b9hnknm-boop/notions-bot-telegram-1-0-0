"""Фабрика ИИ-провайдера: выбирает реализацию по настройке AI_PROVIDER."""
from __future__ import annotations

from ai.base import AIProvider
from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)


def get_provider() -> AIProvider:
    provider = settings.ai_provider
    if provider == "gemini":
        from ai.gemini import GeminiProvider
        return GeminiProvider()
    if provider == "gigachat":
        from ai.gigachat import GigaChatProvider
        return GigaChatProvider()
    raise RuntimeError(
        f"Неизвестный AI_PROVIDER='{provider}'. Допустимо: gemini | gigachat."
    )
