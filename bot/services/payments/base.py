from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True)
class PaymentContext:
    order_id: int
    amount: Decimal
    currency: str
    user_id: int
    customer_name: str


@dataclass(slots=True)
class PaymentInstructions:
    provider: str
    text: str
    external_id: str | None = None
    payment_url: str | None = None
    payment_status: str | None = None
    payment_currency: str | None = None
    payment_network: str | None = None
    payment_amount: Decimal | None = None


class BasePaymentService(ABC):
    provider_code: str

    @abstractmethod
    def checkout_hint(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def create_payment(self, context: PaymentContext) -> PaymentInstructions:
        raise NotImplementedError

    def supports_status_polling(self) -> bool:
        return False

    async def fetch_payment_status(self, *, external_payment_id: str | None, order_id: int) -> dict:
        raise RuntimeError(f"Провайдер {self.provider_code} не поддерживает polling статуса платежа.")

    def verify_webhook_payload(self, raw_body: bytes, headers: dict[str, str] | None = None) -> bool:
        return False
