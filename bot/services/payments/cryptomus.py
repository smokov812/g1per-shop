from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bot.config import Config
from bot.services.payments.base import BasePaymentService, PaymentContext, PaymentInstructions


logger = logging.getLogger(__name__)


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
        invoice_currency = self.config.currency
        to_currency = self.config.cryptomus_to_currency or None
        network = self.config.cryptomus_network or None
        is_crypto_invoice = bool(to_currency) or invoice_currency.upper() not in {"USD", "EUR", "RUB", "UAH", "KZT", "BYN", "TRY"}

        payload = {
            "amount": f"{context.amount:.2f}",
            "currency": invoice_currency,
            "order_id": str(context.order_id),
            "to_currency": to_currency,
            "network": network if (network and is_crypto_invoice) else None,
            "url_callback": self.config.cryptomus_webhook_url or None,
            "url_return": self.config.cryptomus_return_url or None,
            "url_success": self.config.cryptomus_success_url or None,
            "is_payment_multiple": False,
            "lifetime": 3600,
        }
        payload = {key: value for key, value in payload.items() if value not in (None, "")}

        try:
            response = await asyncio.to_thread(self._request_sync, self.create_invoice_url, payload)
        except RuntimeError as exc:
            if "1010" not in str(exc):
                raise

            fallback_payload = {
                "amount": payload["amount"],
                "currency": payload["currency"],
                "order_id": payload["order_id"],
            }
            if to_currency:
                fallback_payload["to_currency"] = to_currency
            if network and is_crypto_invoice:
                fallback_payload["network"] = network

            logger.warning(
                "Cryptomus returned 1010 for full invoice payload, retrying with minimal payload. "
                "order_id=%s currency=%s to_currency=%s network=%s",
                payload.get("order_id"),
                payload.get("currency"),
                payload.get("to_currency"),
                payload.get("network"),
            )
            response = await asyncio.to_thread(self._request_sync, self.create_invoice_url, fallback_payload)

        payment_url = response.get("url") or response.get("payment_url")
        payer_amount = Decimal(str(response.get("payer_amount") or payload["amount"]))
        payer_currency = str(response.get("payer_currency") or payload["currency"])
        network = str(response.get("network") or self.config.cryptomus_network or "")
        expired_at = self._format_expired_at(response.get("expired_at") or response.get("expired_date"))
        status = str(response.get("status") or "check")

        lines = [
            f"<b>Заказ #{context.order_id} создан.</b>",
            "",
            "Счет сформирован через <b>Cryptomus</b>.",
            f"К оплате: <b>{payer_amount:.2f} {payer_currency}</b>",
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
                "User-Agent": "G1perShopBot/1.0",
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
            logger.warning(
                "Cryptomus HTTP error. payload=%s raw=%s",
                self._sanitize_payload(payload),
                raw,
            )
            raise RuntimeError(self._format_error_message(raw)) from exc
        except URLError as exc:
            raise RuntimeError(f"Cryptomus network error: {exc}") from exc

        decoded = json.loads(raw)
        if decoded.get("state") not in (0, None):
            logger.warning(
                "Cryptomus returned non-success state. payload=%s raw=%s",
                self._sanitize_payload(payload),
                raw,
            )
            raise RuntimeError(self._format_error_message(raw))
        result = decoded.get("result")
        if not isinstance(result, dict):
            logger.warning(
                "Cryptomus returned unexpected payload shape. payload=%s raw=%s",
                self._sanitize_payload(payload),
                raw,
            )
            raise RuntimeError(self._format_error_message(raw))
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

    @staticmethod
    def _format_expired_at(value) -> str | None:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M UTC")
        value_str = str(value).strip()
        if value_str.isdigit():
            dt = datetime.fromtimestamp(int(value_str), tz=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M UTC")
        return value_str

    @staticmethod
    def _sanitize_payload(payload: dict) -> dict:
        return {
            key: value
            for key, value in payload.items()
            if key not in {"sign"}
        }

    @staticmethod
    def _format_error_message(raw: str) -> str:
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return f"Cryptomus API error: {raw}"

        parts: list[str] = []
        state = decoded.get("state")
        message = decoded.get("message")
        errors = decoded.get("errors")
        result = decoded.get("result")

        if state is not None:
            parts.append(f"state={state}")
        if message:
            parts.append(str(message))
        if errors:
            parts.append(f"errors={errors}")
        if isinstance(result, dict):
            code = result.get("code")
            if code is not None:
                parts.append(f"code={code}")
        elif result not in (None, ""):
            parts.append(f"result={result}")

        if not parts:
            return f"Cryptomus API error: {raw}"
        return "Cryptomus API error: " + "; ".join(parts)


