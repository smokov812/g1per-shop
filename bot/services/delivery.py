from __future__ import annotations

from html import escape

from aiogram import Bot

from bot.db.repositories import OrderRepository


def _chunks(value: str, size: int = 3500) -> list[str]:
    return [value[i:i + size] for i in range(0, len(value), size)] or [""]


async def deliver_order_digital_content(*, bot: Bot, session_maker, order_id: int) -> bool:
    async with session_maker() as session:
        order = await OrderRepository(session).get(order_id)

    if not order or order.delivery_sent_at:
        return False

    deliverable_items = [item for item in order.items if item.delivery_content]
    if not deliverable_items:
        return False

    await bot.send_message(
        order.user_id,
        f"<b>Ваш заказ #{order.id} оплачен.</b>\n\nНиже цифровой контент по заказу.",
    )

    for item in deliverable_items:
        await bot.send_message(order.user_id, f"<b>{escape(item.title)}</b>")
        for chunk in _chunks(item.delivery_content or ""):
            await bot.send_message(order.user_id, f"<pre>{escape(chunk)}</pre>")

    async with session_maker() as session:
        updated_order = await OrderRepository(session).mark_delivery_sent(order_id)

    return updated_order is not None
