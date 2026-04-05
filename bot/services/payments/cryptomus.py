from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bot.config import Config
from bot.services.payments.base import BasePaymentService, PaymentContext, PaymentInstructions


class CryptomusPaymentService(BasePaymentService):
    provider_code = "cryptomus"
    create_invoice_url = "https://api.cryptomus.com/v1/payment"
    payment_info_url = "https://api.cryptomus.com/v1/payment/info"

    def __init__(self, config: Config) -> None:
        self.config = config

    def checkout_hint(self) -> str:
        return (
            "После подтверждения бот создаст ссылку на оплату через <b>Cryptomus</b>. "
            "После оплаты статус заказа обновится автоматически по webhook или резервной проверке статуса."
        )

    def supports_status_polling(self) -> bool:
        return True

    async def create_payment(self, context: PaymentContext) -> PaymentInstructions:
        payload = {
            "amount": f"{context.amount:.2f}",
            "currency": self.config.currency,
            "order_id": str(context.order_id),
            "network": self.config.cryptomus_network or None,
            "url_callback": self.config.cryptomus_webhook_url or None,
            "url_return": self.config.cryptomus_return_url or None,
            "url_success": self.config.cryptomus_success_url or None,
            "is_payment_multiple": False,
            "lifetime": 3600,
        }
        payload = {key: value for key, value in payload.items() if value not in (None, "")}

        response = await asyncio.to_thread(self._request_sync, self.create_invoice_url, payload)

        payment_url = response.get("url") or response.get("payment_url")
        payer_amount = Decimal(str(response.get("payer_amount") or payload["amount"]))
        payer_currency = str(response.get("payer_currency") or payload["currency"])
        network = str(response.get("network") or self.config.cryptomus_network or "не указана")
        expired_at = response.get("expired_at") or response.get("expired_date")
        status = str(response.get("status") or "check")

        lines = [
            f"<b>Заказ #{context.order_id} создан.</b>",
            "",
            "Счет сформирован через <b>Cryptomus</b>.",
            f"К оплате: <b>{payer_amount:.2f} {payer_currency}</b>",
            f"Сеть: <b>{network}</b>",
        ]

        if expired_at:
            lines.append(f"Счет действует до: <b>{expired_at}</b>")
        if payment_url:
            lines.extend(["", f"Ссылка на оплату:\n{payment_url}"])

        lines.extend(
            [
                "",
                "После оплаты статус заказа обновится автоматически, даже если webhook придет с задержкой.",
            ]
        )

        return PaymentInstructions(
            provider=self.provider_code,
            text="\n".join(lines),
            external_id=response.get("uuid"),
            payment_url=payment_url,
            payment_status=status,
            payment_currency=payer_currency,
            payment_network=network,
            payment_amount=payer_amount,
        )

    async def fetch_payment_status(self, *, external_payment_id: str | None, order_id: int) -> dict:
        payload = {"uuid": external_payment_id} if external_payment_id else {"order_id": str(order_id)}
        return await asyncio.to_thread(self._request_sync, self.payment_info_url, payload)

    def verify_webhook_payload(self, raw_body: bytes, headers: dict[str, str] | None = None) -> bool:
        if not headers:
            return False
        sign = headers.get("sign") or headers.get("Sign") or headers.get("SIGN")
        if not sign:
            return False
        payload = json.loads(raw_body.decode("utf-8"))
        expected = self._build_signature(payload)
        return hmac.compare_digest(expected, sign)

    def _request_sync(self, url: str, payload: dict) -> dict:
        body = self._serialize_payload(payload)
        signature = self._build_signature(payload)

        request = Request(
            url,
            data=body.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "merchant": self.config.cryptomus_merchant_id,
                "sign": signature,
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Cryptomus API error: {raw}") from exc
        except URLError as exc:
            raise RuntimeError(f"Cryptomus network error: {exc}") from exc

        decoded = json.loads(raw)
        result = decoded.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"Cryptomus invalid response: {raw}")
        return result

    def _build_signature(self, payload: dict) -> str:
        body = self._serialize_payload(payload)
        encoded_body = base64.b64encode(body.encode("utf-8")).decode("utf-8")
        return hashlib.md5(f"{encoded_body}{self.config.cryptomus_api_key}".encode("utf-8")).hexdigest()

    @staticmethod
    def _serialize_payload(payload: dict) -> str:
        clean_payload = dict(payload)
        clean_payload.pop("sign", None)
        return json.dumps(clean_payload, ensure_ascii=False, separators=(",", ":")).replace("/", "\\/")
