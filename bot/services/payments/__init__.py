from bot.services.payments.base import BasePaymentService, PaymentContext, PaymentInstructions
from bot.services.payments.cryptomus import CryptomusPaymentService
from bot.services.payments.lzt_market import LztMarketPaymentService
from bot.services.payments.manual import ManualCryptoPaymentService


def create_payment_services(config) -> dict[str, BasePaymentService]:
    services: dict[str, BasePaymentService] = {}
    for provider in config.enabled_payment_providers:
        if provider == ManualCryptoPaymentService.provider_code:
            services[provider] = ManualCryptoPaymentService(config)
            continue

        if provider == CryptomusPaymentService.provider_code:
            if not config.cryptomus_merchant_id or not config.cryptomus_api_key:
                raise RuntimeError(
                    "Для ENABLED_PAYMENT_PROVIDERS=cryptomus нужно заполнить CRYPTOMUS_MERCHANT_ID и CRYPTOMUS_API_KEY."
                )
            services[provider] = CryptomusPaymentService(config)
            continue

        if provider == LztMarketPaymentService.provider_code:
            if not config.lzt_market_api_key or not config.lzt_market_merchant_id:
                raise RuntimeError(
                    "Для ENABLED_PAYMENT_PROVIDERS=lzt_market нужно заполнить LZT_MARKET_API_KEY и LZT_MARKET_MERCHANT_ID."
                )
            services[provider] = LztMarketPaymentService(config)
            continue

        raise RuntimeError(f"Неподдерживаемый PAYMENT_PROVIDER: {provider}.")

    return services


__all__ = [
    "BasePaymentService",
    "CryptomusPaymentService",
    "LztMarketPaymentService",
    "ManualCryptoPaymentService",
    "PaymentContext",
    "PaymentInstructions",
    "create_payment_services",
]
