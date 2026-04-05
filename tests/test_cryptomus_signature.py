from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from bot.services.payments.cryptomus import CryptomusPaymentService


class CryptomusSignatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CryptomusPaymentService(
            SimpleNamespace(
                currency="USDT",
                cryptomus_network="TRON",
                cryptomus_webhook_url="https://example.com/webhooks/cryptomus",
                cryptomus_return_url="https://example.com/return",
                cryptomus_success_url="https://example.com/success",
                cryptomus_merchant_id="merchant-id",
                cryptomus_api_key="secret-key",
            )
        )

    def test_verify_webhook_payload_accepts_valid_signature(self) -> None:
        payload = {"uuid": "payment-1", "order_id": "42", "status": "paid", "is_final": True}
        signature = self.service._build_signature(payload)
        raw_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertTrue(self.service.verify_webhook_payload(raw_body, {"sign": signature}))

    def test_verify_webhook_payload_rejects_invalid_signature(self) -> None:
        payload = {"uuid": "payment-1", "order_id": "42", "status": "paid", "is_final": True}
        raw_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertFalse(self.service.verify_webhook_payload(raw_body, {"sign": "broken"}))


if __name__ == "__main__":
    unittest.main()
