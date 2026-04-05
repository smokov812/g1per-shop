from __future__ import annotations

import logging
from datetime import datetime

from aiohttp import web
from aiogram import Bot
from sqlalchemy import text

from bot.config import Config
from bot.db.repositories import PaymentRepository
from bot.services.payments.cryptomus import CryptomusPaymentService
from bot.texts import order_text

logger = logging.getLogger(__name__)


def create_webhook_app(*, config: Config, session_maker, bot: Bot) -> web.Application:
    app = web.Application()
    app["config"] = config
    app["session_maker"] = session_maker
    app["bot"] = bot
    app["cryptomus_service"] = CryptomusPaymentService(config)

    app.router.add_get("/", index)
    app.router.add_get("/health", healthcheck)
    app.router.add_get("/ready", readiness)
    if config.cryptomus_webhook_enabled:
        app.router.add_post(config.cryptomus_webhook_path, cryptomus_webhook)
    return app


async def index(request: web.Request) -> web.Response:
    config: Config = request.app["config"]
    return web.json_response(
        {
            "service": "telegram-shop-bot",
            "status": "ok",
            "payment_provider": config.payment_provider,
        }
    )


async def healthcheck(request: web.Request) -> web.Response:
    config: Config = request.app["config"]
    return web.json_response(
        {
            "ok": True,
            "status": "healthy",
            "database_backend": config.database_backend,
            "payment_provider": config.payment_provider,
            "time": datetime.utcnow().isoformat() + "Z",
        }
    )


async def readiness(request: web.Request) -> web.Response:
    config: Config = request.app["config"]
    session_maker = request.app["session_maker"]
    checks: dict[str, str] = {}
    warnings: list[str] = []

    try:
        async with session_maker() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    checks["admin_chat"] = "validated_on_startup"

    if config.payment_provider == "cryptomus":
        if config.cryptomus_merchant_id and config.cryptomus_api_key:
            checks["payment_credentials"] = "ok"
        else:
            checks["payment_credentials"] = "missing cryptomus credentials"

        if config.cryptomus_webhook_enabled:
            checks["payment_webhook"] = "ok" if config.cryptomus_webhook_url else "missing CRYPTOMUS_WEBHOOK_URL"
        else:
            checks["payment_webhook"] = "disabled"

    if config.database_backend == "sqlite":
        warnings.append("SQLite подходит для MVP, но для production при деньгах лучше использовать Postgres.")

    ok = all(value == "ok" or value == "validated_on_startup" or value == "disabled" for value in checks.values())
    status = 200 if ok else 503
    return web.json_response({"ok": ok, "status": "ready" if ok else "not_ready", "checks": checks, "warnings": warnings}, status=status)


async def cryptomus_webhook(request: web.Request) -> web.Response:
    config: Config = request.app["config"]
    session_maker = request.app["session_maker"]
    bot: Bot = request.app["bot"]
    service: CryptomusPaymentService = request.app["cryptomus_service"]

    source_ip = _extract_client_ip(request, config)
    if config.cryptomus_allowed_ips and source_ip not in config.cryptomus_allowed_ips:
        logger.warning("Rejected CryptoMus webhook from ip=%s", source_ip)
        return web.json_response({"ok": False, "error": "forbidden ip"}, status=403)

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    if not service.verify_webhook_payload(payload):
        logger.warning("Rejected CryptoMus webhook with invalid signature")
        return web.json_response({"ok": False, "error": "invalid sign"}, status=403)

    async with session_maker() as session:
        result = await PaymentRepository(session).process_cryptomus_callback(payload, source="webhook", source_ip=source_ip)

    if result.order and not result.duplicate and result.current_status != result.previous_status:
        await notify_payment_update(bot=bot, config=config, order=result.order)

    return web.json_response(
        {
            "ok": True,
            "duplicate": result.duplicate,
            "applied": result.applied,
            "order_id": result.order.id if result.order else None,
        }
    )


async def notify_payment_update(*, bot: Bot, config: Config, order) -> None:
    status_label = order.payment_status or order.status or "updated"
    try:
        await bot.send_message(
            order.user_id,
            f"Статус вашего заказа <b>#{order.id}</b> обновлен автоматически: <b>{status_label}</b>.",
        )
    except Exception:
        logger.exception("Failed to notify user about payment update for order=%s", order.id)

    try:
        await bot.send_message(config.admin_id, order_text(order, config.currency, include_customer=True))
    except Exception:
        logger.exception("Failed to notify admin about payment update for order=%s", order.id)



def _extract_client_ip(request: web.Request, config: Config) -> str:
    if config.trust_proxy_headers:
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()
    return request.remote or "unknown"
