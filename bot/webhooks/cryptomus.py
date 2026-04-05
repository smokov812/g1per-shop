from __future__ import annotations

import json
import logging
from datetime import datetime

from aiohttp import web
from aiogram import Bot
from sqlalchemy import text

from bot.config import Config
from bot.db.repositories import PaymentRepository
from bot.services.delivery import deliver_order_digital_content
from bot.services.payments.cryptomus import CryptomusPaymentService
from bot.services.payments.lzt_market import LztMarketPaymentService
from bot.texts import order_text

logger = logging.getLogger(__name__)


def create_webhook_app(*, config: Config, session_maker, bot: Bot) -> web.Application:
    app = web.Application()
    app["config"] = config
    app["session_maker"] = session_maker
    app["bot"] = bot
    app["cryptomus_service"] = CryptomusPaymentService(config)
    app["lzt_service"] = LztMarketPaymentService(config)

    app.router.add_get("/", index)
    app.router.add_get("/health", healthcheck)
    app.router.add_get("/ready", readiness)
    app.router.add_get("/success", generic_success_page)
    app.router.add_get("/return", generic_success_page)
    app.router.add_get("/lzt-success", lzt_success_page)
    if config.cryptomus_webhook_enabled:
        app.router.add_post(config.cryptomus_webhook_path, cryptomus_webhook)
    if config.lzt_market_webhook_enabled:
        app.router.add_post(config.lzt_market_webhook_path, lzt_market_webhook)
    return app


async def index(request: web.Request) -> web.Response:
    config: Config = request.app["config"]
    return web.json_response({"service": "telegram-shop-bot", "status": "ok", "payment_providers": list(config.enabled_payment_providers)})


async def healthcheck(request: web.Request) -> web.Response:
    config: Config = request.app["config"]
    return web.json_response(
        {
            "ok": True,
            "status": "healthy",
            "database_backend": config.database_backend,
            "payment_providers": list(config.enabled_payment_providers),
            "time": datetime.utcnow().isoformat() + "Z",
        }
    )


async def generic_success_page(request: web.Request) -> web.Response:
    return web.Response(
        text="<html><body style=\"font-family:sans-serif;padding:24px;\"><h2>Платеж обработан</h2><p>Можно вернуться в Telegram-бота. Статус заказа обновится автоматически после подтверждения оплаты.</p></body></html>",
        content_type="text/html",
    )


async def lzt_success_page(request: web.Request) -> web.Response:
    return web.Response(
        text="<html><body style=\"font-family:sans-serif;padding:24px;\"><h2>Оплата в LOLZ Market завершена</h2><p>Можно закрыть страницу и вернуться в Telegram-бота. Если платеж уже прошел, статус заказа обновится автоматически.</p></body></html>",
        content_type="text/html",
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

    if "cryptomus" in config.enabled_payment_providers:
        checks["cryptomus_credentials"] = "ok" if config.cryptomus_merchant_id and config.cryptomus_api_key else "missing"
        checks["cryptomus_webhook"] = "ok" if (not config.cryptomus_webhook_enabled or config.cryptomus_webhook_url) else "missing webhook url"

    if "lzt_market" in config.enabled_payment_providers:
        checks["lzt_credentials"] = "ok" if config.lzt_market_api_key and config.lzt_market_merchant_id else "missing"
        checks["lzt_webhook"] = "ok" if (not config.lzt_market_webhook_enabled or config.lzt_market_webhook_url) else "missing webhook url"

    if config.database_backend == "sqlite":
        warnings.append("SQLite подходит для MVP, но для production при деньгах лучше использовать Postgres.")

    ok = all(value in {"ok", "validated_on_startup"} for value in checks.values())
    status = 200 if ok else 503
    return web.json_response({"ok": ok, "status": "ready" if ok else "not_ready", "checks": checks, "warnings": warnings}, status=status)


async def cryptomus_webhook(request: web.Request) -> web.Response:
    config: Config = request.app["config"]
    session_maker = request.app["session_maker"]
    bot: Bot = request.app["bot"]
    service: CryptomusPaymentService = request.app["cryptomus_service"]

    source_ip = _extract_client_ip(request, config)
    if config.cryptomus_allowed_ips and source_ip not in config.cryptomus_allowed_ips:
        logger.warning("Rejected Cryptomus webhook from ip=%s", source_ip)
        return web.json_response({"ok": False, "error": "forbidden ip"}, status=403)

    raw_body = await request.read()
    if not service.verify_webhook_payload(raw_body, dict(request.headers)):
        logger.warning("Rejected Cryptomus webhook with invalid signature")
        return web.json_response({"ok": False, "error": "invalid sign"}, status=403)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    async with session_maker() as session:
        result = await PaymentRepository(session).process_cryptomus_callback(payload, source="webhook", source_ip=source_ip)

    if result.order and not result.duplicate and result.current_status != result.previous_status:
        await notify_payment_update(bot=bot, config=config, order=result.order)
        if result.current_status in {"paid", "completed"}:
            await deliver_order_digital_content(bot=bot, session_maker=session_maker, order_id=result.order.id, admin_id=config.admin_id, manager_username=config.order_manager_username)

    return web.json_response({"ok": True, "duplicate": result.duplicate, "applied": result.applied, "order_id": result.order.id if result.order else None})


async def lzt_market_webhook(request: web.Request) -> web.Response:
    config: Config = request.app["config"]
    session_maker = request.app["session_maker"]
    bot: Bot = request.app["bot"]
    service: LztMarketPaymentService = request.app["lzt_service"]

    raw_body = await request.read()
    signature_valid = service.verify_webhook_payload(raw_body, dict(request.headers))
    if not signature_valid:
        if config.lzt_market_strict_webhook_signature:
            logger.warning("Rejected LOLZ Market webhook with invalid signature")
            return web.json_response({"ok": False, "error": "invalid sign"}, status=403)
        logger.warning("LOLZ Market webhook signature did not match, but strict mode is disabled; processing callback anyway")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    source_ip = _extract_client_ip(request, config)
    async with session_maker() as session:
        result = await PaymentRepository(session).process_lzt_callback(payload, source="webhook", source_ip=source_ip)

    if result.order and not result.duplicate and result.current_status != result.previous_status:
        await notify_payment_update(bot=bot, config=config, order=result.order)
        if result.current_status in {"paid", "completed"}:
            await deliver_order_digital_content(bot=bot, session_maker=session_maker, order_id=result.order.id, admin_id=config.admin_id, manager_username=config.order_manager_username)

    return web.json_response({"ok": True, "duplicate": result.duplicate, "applied": result.applied, "order_id": result.order.id if result.order else None})


async def notify_payment_update(*, bot: Bot, config: Config, order) -> None:
    status_label = order.payment_status or order.status or "updated"
    try:
        await bot.send_message(order.user_id, f"Статус вашего заказа <b>#{order.id}</b> обновлен автоматически: <b>{status_label}</b>.")
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



