"""Service-specific configuration; credentials are never logged."""
import os
from dataclasses import dataclass, field
from urllib.parse import urlparse


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value.strip():
        raise ValueError(f"{name} is required")
    return value


def service_url(name: str) -> str:
    value = required(name).rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(f"{name} must be an HTTP service URL")
    return value


def numeric(name: str, *, positive: bool = False) -> int:
    value = required(name)
    if not value.lstrip("-").isdigit():
        raise ValueError(f"{name} must be an integer")
    number = int(value)
    if number == 0 or (positive and number < 0):
        raise ValueError(f"{name} has an invalid value")
    return number


@dataclass(frozen=True)
class MCPConfig:
    internal_api_token: str = field(repr=False)
    bot_api_url: str

    @classmethod
    def from_env(cls) -> "MCPConfig":
        return cls(required("INTERNAL_API_TOKEN"), service_url("BOT_API_URL"))


@dataclass(frozen=True)
class BotConfig:
    internal_api_token: str = field(repr=False)
    telegram_bot_token: str = field(repr=False)
    telegram_chat_id: int
    telegram_allowed_user_id: int
    hitl_api_url: str

    @classmethod
    def from_env(cls) -> "BotConfig":
        return cls(required("INTERNAL_API_TOKEN"), required("TELEGRAM_BOT_TOKEN"), numeric("TELEGRAM_CHAT_ID"), numeric("TELEGRAM_ALLOWED_USER_ID", positive=True), service_url("HITL_API_URL"))
