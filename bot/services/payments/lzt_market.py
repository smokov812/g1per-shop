from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bot.config import Config
from bot.services.payments.base import BasePaymentService, PaymentContext, PaymentInstructions


class LztMarketPaymentService(BasePaymentService):
    provider_code = "lzt_market"
    invoice_url = "https://prod-api.lzt.market/invoice"

    def __init__(self, config: Config) -> None:
        self.config = config

    def checkout_hint(self) -> str:
        return (
            "После подтверждения бот создаст счет через <b>LOLZ Market</b>. "
            "После оплаты статус заказа обновится автоматически по webhook или резервной проверке инвойса."
        )

    def supports_status_polling(self) -> bool:
        return True

    async def create_payment(self, context: PaymentContext) -> PaymentInstructions:
        payload = {
            "currency": self.config.lzt_market_currency,
            "amount": float(context.amount),
            "payment_id": str(context.order_id),
            "comment": f"Order #{context.order_id}",
            "url_success": self.config.lzt_market_success_url or None,
            "url_callback": self.config.lzt_market_webhook_url or None,
            "merchant_id": self._merchant_id_value(),
            "lifetime": self.config.lzt_market_lifetime_minutes * 60,
        }
        payload = {key: value for key, value in payload.items() if value not in (None, "")}

        response = await asyncio.to_thread(self._request_sync, method="POST", url=self.invoice_url, payload=payload)

        external_id = self._string(response.get("invoice_id") or response.get("id") or response.get("payment_id") or payload["payment_id"])
        payment_url = self._string(response.get("url") or response.get("payment_url") or response.get("link"))
        status = self._string(response.get("status")) or "created"
        amount = Decimal(str(response.get("amount") or context.amount))
        currency = self._string(response.get("currency")) or self.config.lzt_market_currency

        lines = [
            f"<b>Заказ #{context.order_id} создан.</b>",
            "",
            "Счет сформирован через <b>LOLZ Market</b>.",
            f"К оплате: <b>{amount:.2f} {currency}</b>",
        ]
        if payment_url:
            lines.extend(["", f"Ссылка на оплату:\n{payment_url}"])
        lines.extend(["", "После оплаты бот обновит статус автоматически."])

        return PaymentInstructions(
            provider=self.provider_code,
            text="\n".join(lines),
            external_id=external_id,
            payment_url=payment_url,
            payment_status=status,
            payment_currency=currency,
            payment_amount=amount,
        )

    async def fetch_payment_status(self, *, external_payment_id: str | None, order_id: int) -> dict:
        params = {"invoice_id": external_payment_id} if external_payment_id and not external_payment_id.isdigit() else None
        if external_payment_id and external_payment_id.isdigit():
            params = {"invoice_id": external_payment_id}
        if not params:
            params = {"payment_id": str(order_id)}
        return await asyncio.to_thread(self._request_sync, method="GET", url=self.invoice_url, payload=params)

    def verify_webhook_payload(self, raw_body: bytes, headers: dict[str, str] | None = None) -> bool:
        if not self.config.lzt_market_merchant_secret:
            return False
        if not headers:
            return False

        candidates = [
            headers.get("X-Signature"),
            headers.get("x-signature"),
            headers.get("Signature"),
            headers.get("signature"),
            headers.get("X-Hub-Signature-256"),
            headers.get("x-hub-signature-256"),
            headers.get("X-Hub-Signature"),
            headers.get("x-hub-signature"),
        ]
        candidates = [candidate for candidate in candidates if candidate]
        if not candidates:
            return False

        sha256_hex = hmac.new(self.config.lzt_market_merchant_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        sha1_hex = hmac.new(self.config.lzt_market_merchant_secret.encode("utf-8"), raw_body, hashlib.sha1).hexdigest()
        expected_values = {
            sha256_hex,
            f"sha256={sha256_hex}",
            sha1_hex,
            f"sha1={sha1_hex}",
        }
        return any(hmac.compare_digest(candidate, expected) for candidate in candidates for expected in expected_values)

    def _request_sync(self, *, method: str, url: str, payload: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self.config.lzt_market_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        request_url = url
        data = None
        if method == "GET":
            request_url = f"{url}?{urlencode(payload)}"
        else:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        request = Request(request_url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LZT Market API error: {raw}") from exc
        except URLError as exc:
            raise RuntimeError(f"LZT Market network error: {exc}") from exc

        decoded = json.loads(raw)
        if isinstance(decoded, dict):
            data = decoded.get("data")
            if isinstance(data, dict):
                return data
            return decoded
        raise RuntimeError(f"LZT Market invalid response: {raw}")

    def _merchant_id_value(self) -> int | str:
        return int(self.config.lzt_market_merchant_id) if self.config.lzt_market_merchant_id.isdigit() else self.config.lzt_market_merchant_id

    @staticmethod
    def _string(value) -> str | None:
        if value in (None, ""):
            return None
        return str(value)

