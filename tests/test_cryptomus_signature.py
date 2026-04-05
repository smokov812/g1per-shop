from __future__ import annotations

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
        signed_payload = dict(payload)
        signed_payload["sign"] = self.service._build_signature(payload)
        self.assertTrue(self.service.verify_webhook_payload(signed_payload))

    def test_verify_webhook_payload_rejects_invalid_signature(self) -> None:
        payload = {"uuid": "payment-1", "order_id": "42", "status": "paid", "is_final": True, "sign": "broken"}
        self.assertFalse(self.service.verify_webhook_payload(payload))


if __name__ == "__main__":
    unittest.main()
