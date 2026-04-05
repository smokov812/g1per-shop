from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


SUPPORTED_PAYMENT_PROVIDERS = {"manual_crypto", "cryptomus", "lzt_market"}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return float(value.strip())


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value.strip())


def _env_list(name: str, default: str = "") -> tuple[str, ...]:
    value = os.getenv(name, default)
    items = [item.strip() for item in value.split(",") if item.strip()]
    return tuple(items)


@dataclass(slots=True)
class Config:
    bot_token: str
    admin_id: int
    database_url: str
    currency: str
    payment_message: str
    payment_provider: str
    enabled_payment_providers: tuple[str, ...]
    crypto_asset: str
    crypto_network: str
    crypto_wallet: str
    cryptomus_merchant_id: str
    cryptomus_api_key: str
    cryptomus_network: str
    cryptomus_return_url: str
    cryptomus_success_url: str
    cryptomus_webhook_url: str
    cryptomus_webhook_enabled: bool
    cryptomus_webhook_path: str
    cryptomus_allowed_ips: tuple[str, ...]
    lzt_market_api_key: str
    lzt_market_merchant_id: str
    lzt_market_merchant_secret: str
    lzt_market_currency: str
    lzt_market_success_url: str
    lzt_market_webhook_url: str
    lzt_market_webhook_enabled: bool
    lzt_market_webhook_path: str
    lzt_market_lifetime_minutes: int
    web_server_enabled: bool
    web_server_host: str
    web_server_port: int
    trust_proxy_headers: bool
    payment_sync_enabled: bool
    payment_sync_interval_seconds: int
    payment_sync_stale_seconds: int
    payment_sync_batch_size: int
    message_rate_limit_seconds: float
    callback_rate_limit_seconds: float

    @property
    def database_backend(self) -> str:
        if self.database_url.startswith("sqlite"):
            return "sqlite"
        if self.database_url.startswith("postgresql"):
            return "postgresql"
        return "other"



def load_config() -> Config:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=env_path, override=True)

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    admin_id_raw = os.getenv("ADMIN_ID", "").strip()
    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///shop.db").strip()
    currency = os.getenv("CURRENCY", "USDT").strip() or "USDT"
    payment_provider = os.getenv("PAYMENT_PROVIDER", "manual_crypto").strip() or "manual_crypto"
    enabled_payment_providers = _normalize_payment_providers(
        _env_list("ENABLED_PAYMENT_PROVIDERS", payment_provider)
    )
    crypto_asset = os.getenv("CRYPTO_ASSET", currency).strip() or currency
    crypto_network = os.getenv("CRYPTO_NETWORK", "TRC20").strip() or "TRC20"
    crypto_wallet = os.getenv("CRYPTO_WALLET", "").strip()
    cryptomus_merchant_id = os.getenv("CRYPTOMUS_MERCHANT_ID", "").strip()
    cryptomus_api_key = os.getenv("CRYPTOMUS_API_KEY", "").strip()
    cryptomus_network = os.getenv("CRYPTOMUS_NETWORK", "").strip()
    cryptomus_return_url = os.getenv("CRYPTOMUS_RETURN_URL", "").strip()
    cryptomus_success_url = os.getenv("CRYPTOMUS_SUCCESS_URL", "").strip()
    cryptomus_webhook_url = os.getenv("CRYPTOMUS_WEBHOOK_URL", "").strip()
    lzt_market_api_key = os.getenv("LZT_MARKET_API_KEY", "").strip()
    lzt_market_merchant_id = os.getenv("LZT_MARKET_MERCHANT_ID", "").strip()
    lzt_market_merchant_secret = os.getenv("LZT_MARKET_MERCHANT_SECRET", "").strip()
    lzt_market_currency = os.getenv("LZT_MARKET_CURRENCY", currency).strip() or currency
    lzt_market_success_url = os.getenv("LZT_MARKET_SUCCESS_URL", "").strip()
    lzt_market_webhook_url = os.getenv("LZT_MARKET_WEBHOOK_URL", "").strip()
    payment_message = os.getenv(
        "PAYMENT_MESSAGE",
        "Оплата принимается только криптовалютой. После оформления админ пришлет реквизиты.",
    ).strip()

    if not bot_token:
        raise RuntimeError("Переменная BOT_TOKEN не задана в .env")
    if not admin_id_raw or not admin_id_raw.lstrip("-").isdigit():
        raise RuntimeError("Переменная ADMIN_ID не задана или не является числом")
    if database_url.startswith("sqlite:///"):
        database_url = database_url.replace("sqlite:///", "sqlite+aiosqlite:///")

    return Config(
        bot_token=bot_token,
        admin_id=int(admin_id_raw),
        database_url=database_url,
        currency=currency,
        payment_message=payment_message,
        payment_provider=payment_provider,
        enabled_payment_providers=enabled_payment_providers,
        crypto_asset=crypto_asset,
        crypto_network=crypto_network,
        crypto_wallet=crypto_wallet,
        cryptomus_merchant_id=cryptomus_merchant_id,
        cryptomus_api_key=cryptomus_api_key,
        cryptomus_network=cryptomus_network,
        cryptomus_return_url=cryptomus_return_url,
        cryptomus_success_url=cryptomus_success_url,
        cryptomus_webhook_url=cryptomus_webhook_url,
        cryptomus_webhook_enabled=_env_bool("CRYPTOMUS_WEBHOOK_ENABLED", False),
        cryptomus_webhook_path=os.getenv("CRYPTOMUS_WEBHOOK_PATH", "/webhooks/cryptomus").strip() or "/webhooks/cryptomus",
        cryptomus_allowed_ips=_env_list("CRYPTOMUS_ALLOWED_IPS", "91.227.144.54"),
        lzt_market_api_key=lzt_market_api_key,
        lzt_market_merchant_id=lzt_market_merchant_id,
        lzt_market_merchant_secret=lzt_market_merchant_secret,
        lzt_market_currency=lzt_market_currency,
        lzt_market_success_url=lzt_market_success_url,
        lzt_market_webhook_url=lzt_market_webhook_url,
        lzt_market_webhook_enabled=_env_bool("LZT_MARKET_WEBHOOK_ENABLED", False),
        lzt_market_webhook_path=os.getenv("LZT_MARKET_WEBHOOK_PATH", "/webhooks/lzt-market").strip() or "/webhooks/lzt-market",
        lzt_market_lifetime_minutes=_env_int("LZT_MARKET_LIFETIME_MINUTES", 60),
        web_server_enabled=_env_bool("WEB_SERVER_ENABLED", True),
        web_server_host=os.getenv("WEB_SERVER_HOST", "0.0.0.0").strip() or "0.0.0.0",
        web_server_port=_env_int("WEB_SERVER_PORT", 8080),
        trust_proxy_headers=_env_bool("TRUST_PROXY_HEADERS", False),
        payment_sync_enabled=_env_bool("PAYMENT_SYNC_ENABLED", True),
        payment_sync_interval_seconds=_env_int("PAYMENT_SYNC_INTERVAL_SECONDS", 60),
        payment_sync_stale_seconds=_env_int("PAYMENT_SYNC_STALE_SECONDS", 180),
        payment_sync_batch_size=_env_int("PAYMENT_SYNC_BATCH_SIZE", 20),
        message_rate_limit_seconds=_env_float("MESSAGE_RATE_LIMIT_SECONDS", 0.8),
        callback_rate_limit_seconds=_env_float("CALLBACK_RATE_LIMIT_SECONDS", 0.4),
    )



def _normalize_payment_providers(providers: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for provider in providers:
        value = provider.strip()
        if not value:
            continue
        if value not in SUPPORTED_PAYMENT_PROVIDERS:
            raise RuntimeError(
                f"Неподдерживаемый payment provider: {value}. Доступные варианты: {', '.join(sorted(SUPPORTED_PAYMENT_PROVIDERS))}."
            )
        if value not in normalized:
            normalized.append(value)

    if not normalized:
        normalized.append("manual_crypto")
    return tuple(normalized)
