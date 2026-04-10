from __future__ import annotations

import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import Config, load_config
from bot.db.repositories import PaymentRepository
from bot.db.session import create_session_maker, init_db
from bot.handlers import get_admin_router, get_common_router, get_user_router
from bot.middlewares import RateLimitMiddleware
from bot.services import BasePaymentService, create_payment_services, deliver_order_digital_content
from bot.webhooks import create_webhook_app, notify_payment_update

logger = logging.getLogger(__name__)


async def set_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="admin", description="Открыть админ-панель"),
        BotCommand(command="products", description="Список товаров для админа"),
        BotCommand(command="orders", description="Список заказов для админа"),
        BotCommand(command="cancel", description="Отменить текущий сценарий"),
    ]
    await bot.set_my_commands(commands)


async def validate_admin_chat(bot: Bot, admin_id: int) -> None:
    try:
        chat = await bot.get_chat(admin_id)
    except TelegramForbiddenError as exc:
        raise RuntimeError(
            "Бот не может писать админу. Откройте чат с ботом и нажмите Start, затем перезапустите приложение."
        ) from exc
    except TelegramBadRequest as exc:
        raise RuntimeError(
            "ADMIN_ID недоступен для этого бота. Проверьте ID, откройте личный чат с ботом и нажмите Start."
        ) from exc

    if chat.type != "private":
        logger.warning("ADMIN_ID=%s указывает не на личный чат, а на %s", admin_id, chat.type)



def validate_runtime_config(config: Config) -> None:
    if config.cryptomus_webhook_enabled and not config.web_server_enabled:
        raise RuntimeError("Нельзя включить webhook Cryptomus при WEB_SERVER_ENABLED=false.")
    if config.lzt_market_webhook_enabled and not config.web_server_enabled:
        raise RuntimeError("Нельзя включить webhook LOLZ Market при WEB_SERVER_ENABLED=false.")
    if config.telegram_webhook_enabled and not config.web_server_enabled:
        raise RuntimeError("Нельзя включить webhook Telegram при WEB_SERVER_ENABLED=false.")

    if "cryptomus" in config.enabled_payment_providers:
        if not config.cryptomus_merchant_id or not config.cryptomus_api_key:
            raise RuntimeError("Для Cryptomus нужно заполнить CRYPTOMUS_MERCHANT_ID и CRYPTOMUS_API_KEY.")
        if config.cryptomus_webhook_enabled and not config.cryptomus_webhook_url:
            raise RuntimeError("При включенном webhook Cryptomus нужно заполнить CRYPTOMUS_WEBHOOK_URL.")

    if "lzt_market" in config.enabled_payment_providers:
        if not config.lzt_market_api_key or not config.lzt_market_merchant_id:
            raise RuntimeError("Для LOLZ Market нужно заполнить LZT_MARKET_API_KEY и LZT_MARKET_MERCHANT_ID.")
        if config.lzt_market_webhook_enabled and not config.lzt_market_webhook_url:
            raise RuntimeError("При включенном webhook LOLZ Market нужно заполнить LZT_MARKET_WEBHOOK_URL.")

    if config.telegram_webhook_enabled and not config.telegram_webhook_url:
        raise RuntimeError("При включенном webhook Telegram нужно заполнить TELEGRAM_WEBHOOK_URL.")

    if config.database_backend == "sqlite":
        logger.warning("Бот запущен на SQLite. Для production при реальных оплатах лучше использовать Postgres.")

    if config.web_server_enabled and config.trust_proxy_headers:
        logger.info("TRUST_PROXY_HEADERS=true: доверяйте этому режиму только за reverse proxy, который ты контролируешь.")


async def start_web_server(*, bot: Bot, config: Config, session_maker, dispatcher: Dispatcher) -> web.AppRunner | None:
    if not config.web_server_enabled:
        return None

    app = create_webhook_app(config=config, session_maker=session_maker, bot=bot, dispatcher=dispatcher)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.web_server_host, config.web_server_port)
    await site.start()
    logger.info("Web server started on %s:%s", config.web_server_host, config.web_server_port)
    return runner


async def payment_sync_worker(*, bot: Bot, config: Config, session_maker, payment_services: dict[str, BasePaymentService]) -> None:
    pollable_services = [service for service in payment_services.values() if service.supports_status_polling()]
    if not config.payment_sync_enabled or not pollable_services:
        return

    logger.info(
        "Payment sync worker enabled: interval=%ss stale=%ss batch=%s providers=%s",
        config.payment_sync_interval_seconds,
        config.payment_sync_stale_seconds,
        config.payment_sync_batch_size,
        ", ".join(service.provider_code for service in pollable_services),
    )

    try:
        while True:
            for service in pollable_services:
                async with session_maker() as session:
                    payments = await PaymentRepository(session).list_stale_pending(
                        provider=service.provider_code,
                        stale_after_seconds=config.payment_sync_stale_seconds,
                        limit=config.payment_sync_batch_size,
                    )

                for payment in payments:
                    try:
                        payload = await service.fetch_payment_status(
                            external_payment_id=payment.external_payment_id,
                            order_id=payment.order_id,
                        )
                    except Exception as exc:
                        logger.warning("Payment sync failed for provider=%s payment_id=%s: %s", service.provider_code, payment.id, exc)
                        async with session_maker() as session:
                            await PaymentRepository(session).mark_sync_error(payment.id, str(exc))
                        continue

                    async with session_maker() as session:
                        repo = PaymentRepository(session)
                        if service.provider_code == "cryptomus":
                            result = await repo.process_cryptomus_callback(payload, source="poll")
                        elif service.provider_code == "lzt_market":
                            result = await repo.process_lzt_callback(payload, source="poll")
                        else:
                            continue

                    if result.order and not result.duplicate and result.current_status != result.previous_status:
                        await notify_payment_update(bot=bot, config=config, order=result.order)
                        if result.current_status in {"paid", "completed"}:
                            await deliver_order_digital_content(bot=bot, session_maker=session_maker, order_id=result.order.id, admin_id=config.admin_id, manager_username=config.order_manager_username)

            await asyncio.sleep(config.payment_sync_interval_seconds)
    except asyncio.CancelledError:
        logger.info("Payment sync worker stopped")
        raise


async def ensure_webhook(*, bot: Bot, url: str, secret_token: str | None, retry_seconds: int = 10) -> None:
    while True:
        try:
            await bot.set_webhook(url=url, secret_token=secret_token, drop_pending_updates=True)
            return
        except TelegramNetworkError as exc:
            logger.warning("Failed to set Telegram webhook: %s. Retry in %ss", exc, retry_seconds)
            await asyncio.sleep(retry_seconds)


async def run_polling() -> None:
    logging.basicConfig(level=logging.INFO)

    config = load_config()
    validate_runtime_config(config)

    engine, session_maker = create_session_maker(config.database_url)
    await init_db(engine)

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher(storage=MemoryStorage())
    payment_services = create_payment_services(config)
    rate_limit = RateLimitMiddleware(
        session_maker=session_maker,
        message_window=config.message_rate_limit_seconds,
        callback_window=config.callback_rate_limit_seconds,
        admin_id=config.admin_id,
    )

    dispatcher["config"] = config
    dispatcher["session_maker"] = session_maker
    dispatcher["payment_services"] = payment_services
    dispatcher.message.middleware(rate_limit)
    dispatcher.callback_query.middleware(rate_limit)

    dispatcher.include_router(
        get_common_router(
            config.admin_id,
            config.support_username,
            offer_url=config.offer_url,
            privacy_url=config.privacy_url,
            terms_url=config.terms_url,
            channel_url=config.channel_url,
        )
    )
    dispatcher.include_router(get_user_router())
    dispatcher.include_router(get_admin_router(config.admin_id))

    try:
        await validate_admin_chat(bot, config.admin_id)
        logger.info("Admin chat validation passed for admin_id=%s", config.admin_id)
    except TelegramNetworkError as exc:
        logger.warning("Unable to validate admin chat due to Telegram API timeout: %s", exc)

    try:
        await set_commands(bot)
    except TelegramNetworkError as exc:
        logger.warning("Unable to set bot commands due to Telegram API timeout: %s", exc)

    webhook_runner = await start_web_server(bot=bot, config=config, session_maker=session_maker, dispatcher=dispatcher)
    sync_task = None
    if config.payment_sync_enabled:
        sync_task = asyncio.create_task(
            payment_sync_worker(bot=bot, config=config, session_maker=session_maker, payment_services=payment_services)
        )

    try:
        if config.telegram_webhook_enabled:
            await ensure_webhook(
                bot=bot,
                url=config.telegram_webhook_url,
                secret_token=config.telegram_webhook_secret or None,
            )
            await asyncio.Event().wait()
        else:
            try:
                await bot.delete_webhook(drop_pending_updates=True)
            except TelegramNetworkError as exc:
                logger.warning("Failed to delete webhook due to Telegram API timeout: %s", exc)
            await dispatcher.start_polling(bot, drop_pending_updates=True)
    finally:
        if sync_task is not None:
            sync_task.cancel()
            await asyncio.gather(sync_task, return_exceptions=True)
        if webhook_runner is not None:
            await webhook_runner.cleanup()
        await bot.session.close()
        await engine.dispose()




