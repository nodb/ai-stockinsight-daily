from __future__ import annotations

import os
from dataclasses import dataclass


def _split_recipients(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    value = _env_str(name)
    if value is None:
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    gemini_model: str
    allow_ai_fallback: bool
    news_limit: int
    max_pages: int
    mail_user: str | None
    mail_pwd: str | None
    mail_to: list[str]
    smtp_host: str
    smtp_port: int
    http_verify_ssl: bool

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            gemini_api_key=_env_str("GEMINI_API_KEY"),
            gemini_model=_env_str("GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash",
            allow_ai_fallback=_env_bool("ALLOW_AI_FALLBACK", False),
            news_limit=_env_int("NEWS_LIMIT", 50),
            max_pages=_env_int("MAX_PAGES", 4),
            mail_user=_env_str("MAIL_USER"),
            mail_pwd=_env_str("MAIL_PWD"),
            mail_to=_split_recipients(os.getenv("MAIL_TO")),
            smtp_host=_env_str("SMTP_HOST", "smtp.gmail.com") or "smtp.gmail.com",
            smtp_port=_env_int("SMTP_PORT", 587),
            http_verify_ssl=_env_bool("HTTP_VERIFY_SSL", True),
        )

    def validate_email(self) -> None:
        missing = []
        if not self.mail_user:
            missing.append("MAIL_USER")
        if not self.mail_pwd:
            missing.append("MAIL_PWD")
        if not self.mail_to:
            missing.append("MAIL_TO")
        if missing:
            raise RuntimeError(f"Missing email environment variables: {', '.join(missing)}")
