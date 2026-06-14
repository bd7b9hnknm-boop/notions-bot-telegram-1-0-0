"""
Пул API-ключей Gemini с ротацией.

Идея: держим несколько ключей. На каждый запрос берём следующий по кругу
(round-robin — чтобы нагрузка распределялась равномерно). Если ключ упёрся
в лимит (HTTP 429 / RESOURCE_EXHAUSTED), помечаем его «на отдых» (cooldown)
и сразу пробуем следующий. Когда все ключи на отдыхе — отдаём понятную ошибку.

Длительность отдыха:
  - похоже на дневной лимит (в тексте есть "day"/"perday") → до полуночи
    по тихоокеанскому времени (там у Gemini сбрасываются суточные квоты);
  - иначе (минутный лимит) → короткая пауза.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from google import genai
from google.genai import errors

from ai.errors import AIError
from utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_COOLDOWN = 65.0          # сек: пауза при минутном лимите
_PACIFIC = ZoneInfo("America/Los_Angeles")


def _seconds_to_pacific_midnight() -> float:
    """Сколько секунд до сброса суточных квот Gemini (полночь PT)."""
    now = datetime.now(_PACIFIC)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (nxt - now).total_seconds()


class _KeyState:
    """Состояние одного ключа: клиент + время, до которого он 'на отдыхе'."""
    __slots__ = ("client", "label", "cooldown_until")

    def __init__(self, key: str, label: str):
        self.client = genai.Client(api_key=key)
        self.label = label
        self.cooldown_until = 0.0  # отметка монотонного времени

    @property
    def available(self) -> bool:
        return time.monotonic() >= self.cooldown_until


class GeminiKeyPool:
    def __init__(self, keys: list[str]):
        if not keys:
            raise RuntimeError("Не задан ни один ключ Gemini (GEMINI_API_KEYS).")
        self.states = [_KeyState(k, f"#{i + 1}") for i, k in enumerate(keys)]
        self._idx = 0
        logger.info("Пул ключей Gemini инициализирован: %d шт.", len(self.states))

    # порядок обхода на этот запрос: начинаем со следующего ключа (round-robin)
    def _order(self) -> list[_KeyState]:
        n = len(self.states)
        start = self._idx % n
        self._idx = (self._idx + 1) % n
        return [self.states[(start + i) % n] for i in range(n)]

    @staticmethod
    def _cooldown_for(err: errors.APIError) -> float:
        blob = f"{getattr(err, 'message', '')} {getattr(err, 'details', '')}".lower()
        if "day" in blob:  # "PerDay", "per day", "daily" — дневная квота
            return _seconds_to_pacific_midnight()
        return _DEFAULT_COOLDOWN

    async def run(self, attempt: Callable[[genai.Client], Awaitable[Any]]) -> Any:
        """
        Выполнить запрос с ротацией ключей.
        `attempt(client)` — корутина, делающая фактический вызов Gemini.
        """
        last_err: Exception | None = None
        skipped = 0

        for state in self._order():
            if not state.available:
                skipped += 1
                continue
            try:
                result = await attempt(state.client)
                return result
            except errors.ClientError as e:
                if e.code == 429:  # лимит/квота — меняем ключ
                    cd = self._cooldown_for(e)
                    state.cooldown_until = time.monotonic() + cd
                    logger.warning(
                        "Ключ %s упёрся в лимит (429). Пауза %.0f c, переключаюсь.",
                        state.label, cd,
                    )
                    last_err = e
                    continue
                # 400/403 и пр. — это не про лимит (битый ключ, плохой запрос)
                raise
            except errors.ServerError as e:  # 5xx — пробуем другой ключ
                logger.warning("Ключ %s: сбой сервера Gemini, пробую следующий.", state.label)
                last_err = e
                continue

        # сюда попали, если ни один ключ не сработал
        if last_err is None and skipped:
            raise AIError("Все ключи временно исчерпали лимит. Попробуй через минуту. 🙏")
        raise AIError(f"Не удалось выполнить запрос к Gemini: {last_err}")
