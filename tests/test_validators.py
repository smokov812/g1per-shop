from __future__ import annotations

import unittest
from decimal import Decimal

from bot.validators import ValidationError, validate_optional_text, validate_price, validate_required_text, validate_sku


class ValidatorTests(unittest.TestCase):
    def test_validate_required_text_trims_value(self) -> None:
        self.assertEqual(validate_required_text("  Test user  ", "Имя", 20), "Test user")

    def test_validate_required_text_rejects_empty_value(self) -> None:
        with self.assertRaises(ValidationError):
            validate_required_text("   ", "Имя", 20)

    def test_validate_optional_text_returns_none_for_blank(self) -> None:
        self.assertIsNone(validate_optional_text("   ", "Комментарий", 50))

    def test_validate_price_returns_decimal(self) -> None:
        self.assertEqual(validate_price("19.99"), Decimal("19.99"))

    def test_validate_sku_accepts_safe_symbols(self) -> None:
        self.assertEqual(validate_sku("SKU_test-01"), "SKU_test-01")


if __name__ == "__main__":
    unittest.main()
