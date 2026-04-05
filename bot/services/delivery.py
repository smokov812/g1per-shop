from __future__ import annotations

from html import escape

from aiogram import Bot

from bot.db.repositories import DeliveryFileRepository, OrderRepository


async def deliver_order_digital_content(*, bot: Bot, session_maker, order_id: int, admin_id: int | None = None) -> bool:
    async with session_maker() as session:
        order = await OrderRepository(session).get(order_id)

    if not order or order.delivery_sent_at:
        return False

    required_by_product: dict[int, int] = {}
    product_titles: dict[int, str] = {}
    text_items = []
    for item in order.items:
        if item.product_id:
            required_by_product[item.product_id] = required_by_product.get(item.product_id, 0) + item.quantity
            product_titles[item.product_id] = item.title
        if item.delivery_content:
            text_items.append(item)

    async with session_maker() as session:
        delivery_repo = DeliveryFileRepository(session)
        reserved_files = await delivery_repo.get_reserved_for_order(order.id)

    reserved_count_by_product: dict[int, int] = {}
    for file in reserved_files:
        reserved_count_by_product[file.product_id] = reserved_count_by_product.get(file.product_id, 0) + 1

    for product_id, required_count in required_by_product.items():
        missing_count = required_count - reserved_count_by_product.get(product_id, 0)
        if missing_count <= 0:
            continue

        async with session_maker() as session:
            delivery_repo = DeliveryFileRepository(session)
            new_files = await delivery_repo.reserve_for_order(
                product_id=product_id,
                order_id=order.id,
                quantity=missing_count,
            )

        if len(new_files) < missing_count:
            title = product_titles.get(product_id, f"ID {product_id}")
            user_text = (
                f"<b>Заказ #{order.id} оплачен.</b>\n\n"
                f"Для товара <b>{escape(title)}</b> сейчас не хватает ZIP-файлов в пуле. "
                "Админ уже уведомлен и отправит выдачу вручную."
            )
            admin_text = (
                f"<b>Не хватает ZIP-файлов для автодоставки</b>\n\n"
                f"Заказ: <b>#{order.id}</b>\n"
                f"Покупатель: <b>{escape(order.customer_name)}</b>\n"
                f"Товар: <b>{escape(title)}</b>\n"
                f"Нужно файлов: <b>{required_count}</b>\n"
                f"Не хватает: <b>{missing_count}</b>"
            )
            try:
                await bot.send_message(order.user_id, user_text)
            except Exception:
                pass
            if admin_id:
                try:
                    await bot.send_message(admin_id, admin_text)
                except Exception:
                    pass
            return False

        reserved_files.extend(new_files)

    pending_files = [file for file in reserved_files if file.delivered_at is None]
    if not pending_files and not text_items:
        return False

    await bot.send_message(
        order.user_id,
        f"<b>Ваш заказ #{order.id} оплачен.</b>\n\nНиже ZIP-файлы по вашему заказу.",
    )

    for file in pending_files:
        caption = f"Заказ #{order.id}"
        if file.file_name:
            caption += f"\n{escape(file.file_name)}"
        await bot.send_document(order.user_id, file.telegram_file_id, caption=caption)
        async with session_maker() as session:
            await DeliveryFileRepository(session).mark_delivered([file.id])

    for item in text_items:
        await bot.send_message(
            order.user_id,
            f"<b>{escape(item.title)}</b>\n\n{escape(item.delivery_content or '')}",
        )

    async with session_maker() as session:
        updated_order = await OrderRepository(session).mark_delivery_sent(order_id)

    return updated_order is not None

