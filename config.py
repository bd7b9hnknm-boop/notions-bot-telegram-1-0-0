"""
Чтение настроек из .env и единая точка доступа к конфигурации.
Используем python-dotenv + простой dataclass, без тяжёлых зависимостей.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Загружаем .env в переменные окружения (если файл есть)
load_dotenv()


def _get_admin_ids(raw: str | None) -> set[int]:
    """Парсим "12345,67890" -> {12345, 67890}."""
    if not raw:
        return set()
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


def _parse_keys(*sources: str | None) -> tuple[str, ...]:
    """
    Собираем ключи из нескольких источников (через запятую), убираем
    пустые и дубликаты, сохраняем порядок. Поддерживает и GEMINI_API_KEYS
    (несколько), и старый GEMINI_API_KEY (один).
    """
    keys: list[str] = []
    for src in sources:
        if not src:
            continue
        for k in src.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    return tuple(keys)


@dataclass(frozen=True)
class Settings:
    # Telegram
    bot_token: str
    bot_name: str

    # ИИ
    ai_provider: str
    gemini_api_keys: tuple[str, ...]   # пул ключей для ротации
    gemini_model: str
    qwen_api_keys: tuple[str, ...]     # ключи Qwen (DashScope)
    qwen_base_url: str
    qwen_model: str
    qwen_asr_model: str                # модель распознавания речи
    gigachat_credentials: str

    # Общее
    timezone: str
    database_path: str
    free_notes_limit: int
    admin_ids: set[int] = field(default_factory=set)

    def validate(self) -> None:
        """Проверяем, что заполнены критичные поля. Бросаем понятную ошибку."""
        missing: list[str] = []
        if not self.bot_token:
            missing.append("BOT_TOKEN")
        if self.ai_provider == "gemini" and not self.gemini_api_keys:
            missing.append("GEMINI_API_KEYS (или GEMINI_API_KEY)")
        if self.ai_provider == "qwen" and not self.qwen_api_keys:
            missing.append("QWEN_API_KEYS (или QWEN_API_KEY)")
        if self.ai_provider == "gigachat" and not self.gigachat_credentials:
            missing.append("GIGACHAT_CREDENTIALS")
        if missing:
            raise RuntimeError(
                "Не заполнены обязательные переменные в .env: "
                + ", ".join(missing)
                + ". Скопируй .env.example в .env и заполни их."
            )


def load_settings() -> Settings:
    return Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        bot_name=os.getenv("BOT_NAME", "Нота").strip() or "Нота",
        ai_provider=os.getenv("AI_PROVIDER", "gemini").strip().lower(),
        gemini_api_keys=_parse_keys(
            os.getenv("GEMINI_API_KEYS"), os.getenv("GEMINI_API_KEY")
        ),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip(),
        qwen_api_keys=_parse_keys(
            os.getenv("QWEN_API_KEYS"), os.getenv("QWEN_API_KEY")
        ),
        qwen_base_url=os.getenv(
            "QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        ).strip(),
        qwen_model=os.getenv("QWEN_MODEL", "qwen-vl-max").strip(),
        qwen_asr_model=os.getenv("QWEN_ASR_MODEL", "qwen3-asr-flash").strip(),
        gigachat_credentials=os.getenv("GIGACHAT_CREDENTIALS", "").strip(),
        timezone=os.getenv("TIMEZONE", "Europe/Moscow").strip(),
        database_path=os.getenv("DATABASE_PATH", "data/bot.db").strip(),
        free_notes_limit=int(os.getenv("FREE_NOTES_LIMIT", "50")),
        admin_ids=_get_admin_ids(os.getenv("ADMIN_IDS")),
    )


# Глобальный объект настроек
settings = load_settings()
