from __future__ import annotations

import asyncio
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from bot.const import OrderStatus
from bot.db.models import Order, PaymentEvent
from bot.db.repositories import OrderRepository, PaymentRepository
from bot.db.session import create_session_maker, init_db


class PaymentRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "payments_test.db"
        self.engine, self.session_maker = create_session_maker(f"sqlite+aiosqlite:///{db_path.as_posix()}")
        await init_db(self.engine)

        async with self.session_maker() as session:
            order = Order(
                user_id=1001,
                username="buyer",
                customer_name="Buyer",
                contact="@buyer",
                comment="test",
                total_amount=Decimal("25.00"),
                status=OrderStatus.AWAITING_PAYMENT.value,
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)
            self.order_id = order.id
            await PaymentRepository(session).register_checkout_payment(
                order_id=order.id,
                provider="cryptomus",
                external_payment_id="payment-uuid-1",
                status="check",
                amount=Decimal("25.00"),
                currency="USDT",
                network="TRON",
                payment_url="https://pay.example/invoice",
            )

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self.temp_dir.cleanup()

    async def test_process_callback_marks_order_as_paid_and_creates_event(self) -> None:
        payload = {
            "uuid": "payment-uuid-1",
            "order_id": str(self.order_id),
            "status": "paid",
            "is_final": True,
            "payer_amount": "25.00",
            "payer_currency": "USDT",
            "network": "TRON",
            "txid": "tx-123",
            "url": "https://pay.example/invoice",
        }

        async with self.session_maker() as session:
            result = await PaymentRepository(session).process_cryptomus_callback(payload, source="webhook", source_ip="127.0.0.1")
            self.assertFalse(result.duplicate)
            self.assertTrue(result.applied)

        async with self.session_maker() as session:
            order = await OrderRepository(session).get(self.order_id)
            payment = await PaymentRepository(session).get_by_provider_and_external_id("cryptomus", "payment-uuid-1")
            events = (await session.execute(select(PaymentEvent))).scalars().all()

        self.assertIsNotNone(order)
        self.assertIsNotNone(payment)
        self.assertEqual(order.status, OrderStatus.PAID.value)
        self.assertEqual(order.payment_txid, "tx-123")
        self.assertEqual(payment.status, "paid")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source, "webhook")

    async def test_duplicate_callback_is_ignored(self) -> None:
        payload = {
            "uuid": "payment-uuid-1",
            "order_id": str(self.order_id),
            "status": "paid",
            "is_final": True,
            "payer_amount": "25.00",
            "payer_currency": "USDT",
        }

        async with self.session_maker() as session:
            await PaymentRepository(session).process_cryptomus_callback(payload, source="webhook", source_ip="127.0.0.1")

        async with self.session_maker() as session:
            second = await PaymentRepository(session).process_cryptomus_callback(payload, source="webhook", source_ip="127.0.0.1")
            self.assertTrue(second.duplicate)
            events = (await session.execute(select(PaymentEvent))).scalars().all()

        self.assertEqual(len(events), 1)


if __name__ == "__main__":
    unittest.main()
