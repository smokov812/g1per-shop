from bot.services.payments.base import BasePaymentService, PaymentContext, PaymentInstructions
from bot.services.payments.cryptomus import CryptomusPaymentService
from bot.services.payments.manual import ManualCryptoPaymentService


def create_payment_service(config) -> BasePaymentService:
    if config.payment_provider == ManualCryptoPaymentService.provider_code:
        return ManualCryptoPaymentService(config)

    if config.payment_provider == CryptomusPaymentService.provider_code:
        if not config.cryptomus_merchant_id or not config.cryptomus_api_key:
            raise RuntimeError(
                "Для PAYMENT_PROVIDER=cryptomus нужно заполнить CRYPTOMUS_MERCHANT_ID и CRYPTOMUS_API_KEY."
            )
        return CryptomusPaymentService(config)

    raise RuntimeError(
        f"Неподдерживаемый PAYMENT_PROVIDER: {config.payment_provider}. "
        "Доступные варианты: manual_crypto, cryptomus."
    )


__all__ = [
    "BasePaymentService",
    "CryptomusPaymentService",
    "ManualCryptoPaymentService",
    "PaymentContext",
    "PaymentInstructions",
    "create_payment_service",
]
