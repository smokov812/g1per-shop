from __future__ import annotations

from html import escape

from aiogram import Bot

from bot.db.repositories import DeliveryFileRepository, OrderRepository


def _normalize_manager_username(manager_username: str | None) -> str:
    value = (manager_username or "").strip()
    if value and not value.startswith("@"):
        value = f"@{value}"
    return value


def _render_delivery_template(template: str | None, *, order, item, manager_username: str | None) -> str:
    if not template:
        return ""

    username = f"@{order.username}" if order.username else f"id:{order.user_id}"
    values = {
        "{order_id}": str(order.id),
        "{username}": username,
        "{user_id}": str(order.user_id),
        "{manager_username}": _normalize_manager_username(manager_username),
        "{product_title}": item.title,
    }

    rendered = template
    for placeholder, value in values.items():
        rendered = rendered.replace(placeholder, value)
    return rendered


async def deliver_order_digital_content(
    *,
    bot: Bot,
    session_maker,
    order_id: int,
    admin_id: int | None = None,
    include_preorder: bool = False,
    manager_username: str | None = None,
) -> bool:
    async with session_maker() as session:
        order = await OrderRepository(session).get(order_id)

    if not order or order.delivery_sent_at:
        return False

    auto_required_by_product: dict[int, int] = {}
    product_titles: dict[int, str] = {}
    text_items = []
    preorder_items = []

    for item in order.items:
        if item.stock_status == "preorder" and not include_preorder:
            preorder_items.append(item)
            continue

        if item.product_id:
            auto_required_by_product[item.product_id] = auto_required_by_product.get(item.product_id, 0) + item.quantity
            product_titles[item.product_id] = item.title
        if item.delivery_content:
            text_items.append(item)

    async with session_maker() as session:
        delivery_repo = DeliveryFileRepository(session)
        reserved_files = await delivery_repo.get_reserved_for_order(order.id)

    reserved_count_by_product: dict[int, int] = {}
    for file in reserved_files:
        reserved_count_by_product[file.product_id] = reserved_count_by_product.get(file.product_id, 0) + 1

    for product_id, required_count in auto_required_by_product.items():
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
    delivery_completed = False

    if pending_files:
        await bot.send_message(
            order.user_id,
            f"<b>Ваш заказ #{order.id} оплачен.</b>\n\nНиже ZIP-файлы по вашему заказу.",
        )
        delivery_completed = True

    for file in pending_files:
        await bot.send_document(order.user_id, file.telegram_file_id, caption=f"Заказ #{order.id}")
        async with session_maker() as session:
            await DeliveryFileRepository(session).mark_delivered([file.id])

    if text_items:
        delivery_completed = True
    for item in text_items:
        rendered_text = _render_delivery_template(item.delivery_content, order=order, item=item, manager_username=manager_username)
        await bot.send_message(
            order.user_id,
            f"<b>{escape(item.title)}</b>\n\n{escape(rendered_text)}",
        )

    normalized_manager = _normalize_manager_username(manager_username)

    preorder_instruction_sent = False
    if preorder_items and normalized_manager:
        for item in preorder_items:
            if not item.post_payment_message:
                continue
            rendered_template = _render_delivery_template(item.post_payment_message, order=order, item=item, manager_username=normalized_manager)
            user_text = (
                f"<b>Заказ #{order.id} оплачен.</b>\n\n"
                f"Позиция <b>{escape(item.title)}</b> оформлена как <b>вход по коду</b>.\n"
                f"Менеджер: <b>{escape(normalized_manager)}</b>\n\n"
                "Отправьте менеджеру этот шаблон сообщения:\n"
                f"<code>{escape(rendered_template)}</code>"
            )
            try:
                await bot.send_message(order.user_id, user_text)
                preorder_instruction_sent = True
            except Exception:
                pass

    if preorder_items and admin_id:
        preorder_titles = ", ".join(escape(item.title) for item in preorder_items)
        admin_text = (
            f"<b>В заказе #{order.id} есть товары под заказ</b>\n\n"
            f"Покупатель: <b>{escape(order.customer_name)}</b>\n"
            f"Позиции: <b>{preorder_titles}</b>\n"
            "Автовыдача для них отключена, нужна ручная обработка."
        )
        try:
            await bot.send_message(admin_id, admin_text)
        except Exception:
            pass

    if not delivery_completed and not preorder_instruction_sent:
        return False

    if delivery_completed:
        async with session_maker() as session:
            updated_order = await OrderRepository(session).mark_delivery_sent(order_id)
        return updated_order is not None

    return True


