from __future__ import annotations

from bot.config import Config
from bot.services.payments.base import BasePaymentService, PaymentContext, PaymentInstructions


class ManualCryptoPaymentService(BasePaymentService):
    provider_code = "manual_crypto"

    def __init__(self, config: Config) -> None:
        self.config = config

    def checkout_hint(self) -> str:
        if self.config.crypto_wallet:
            return (
                f"Оплата принимается в <b>{self.config.crypto_asset}</b> "
                f"через сеть <b>{self.config.crypto_network}</b>. "
                "После создания заказа бот покажет адрес и дальнейшие шаги."
            )
        return self.config.payment_message

    async def create_payment(self, context: PaymentContext) -> PaymentInstructions:
        if self.config.crypto_wallet:
            text = (
                f"<b>Заказ #{context.order_id} создан.</b>\n\n"
                f"К оплате: <b>{context.amount:.2f} {self.config.crypto_asset}</b>\n"
                f"Сеть: <b>{self.config.crypto_network}</b>\n"
                f"Кошелек: <code>{self.config.crypto_wallet}</code>\n\n"
                "После оплаты отправьте админу tx hash или скрин перевода. "
                "В комментарии к сообщению укажите номер заказа."
            )
        else:
            text = (
                f"<b>Заказ #{context.order_id} создан.</b>\n\n"
                f"{self.config.payment_message}\n\n"
                "Сейчас реквизиты для оплаты не заданы в конфиге. "
                "Админ свяжется с вами вручную."
            )

        return PaymentInstructions(
            provider=self.provider_code,
            text=text,
            payment_status="manual_pending",
            payment_currency=self.config.crypto_asset,
            payment_network=self.config.crypto_network,
            payment_amount=context.amount,
        )
