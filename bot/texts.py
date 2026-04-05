from __future__ import annotations

from decimal import Decimal
from html import escape

from bot.const import ORDER_STATUS_LABELS, STOCK_STATUS_LABELS


def format_price(amount: Decimal, currency: str) -> str:
    return f"{amount:.2f} {escape(currency)}"


def product_caption(product, currency: str) -> str:
    lines = [
        f"<b>{escape(product.title)}</b>",
        "",
        f"<b>Цена:</b> {format_price(product.price, currency)}",
        f"<b>Наличие:</b> {escape(STOCK_STATUS_LABELS.get(product.stock_status, product.stock_status))}",
        f"<b>SKU:</b> {escape(product.sku)}",
    ]

    if product.short_description:
        lines.extend(["", f"<b>Кратко:</b> {escape(product.short_description)}"])
    if product.full_description:
        lines.extend(["", f"<b>Описание:</b>\n{escape(product.full_description)}"])
    if product.stock_status == "preorder":
        lines.extend(["", "<b>Выдача:</b> вручную после оплаты"])

    return "\n".join(lines)


def admin_product_caption(product, currency: str) -> str:
    category_name = product.category.title if product.category else "Без категории"
    visibility = "Активен" if product.is_active else "Скрыт"
    available_zip_count = len([item for item in getattr(product, "delivery_files", []) if item.reserved_order_id is None])

    lines = [
        f"<b>Товар #{product.id}</b>",
        f"<b>Название:</b> {escape(product.title)}",
        f"<b>Категория:</b> {escape(category_name)}",
        f"<b>Цена:</b> {format_price(product.price, currency)}",
        f"<b>SKU:</b> {escape(product.sku)}",
        f"<b>Наличие:</b> {escape(STOCK_STATUS_LABELS.get(product.stock_status, product.stock_status))}",
        f"<b>Статус:</b> {escape(visibility)}",
        f"<b>ZIP в пуле:</b> {available_zip_count}",
    ]

    if product.short_description:
        lines.append(f"<b>Краткое описание:</b> {escape(product.short_description)}")
    if product.full_description:
        lines.extend(["<b>Полное описание:</b>", escape(product.full_description)])
    if product.delivery_content:
        lines.append("<b>Текст после выдачи:</b> настроен")
    else:
        lines.append("<b>Текст после выдачи:</b> не задан")
    lines.append("<b>Фото:</b> есть" if product.image else "<b>Фото:</b> нет")
    return "\n".join(lines)


def cart_text(items, currency: str) -> str:
    if not items:
        return "<b>Корзина пуста.</b>\nДобавьте товары из каталога."

    total = Decimal("0")
    lines = ["<b>Корзина</b>", ""]

    for index, item in enumerate(items, start=1):
        if not item.product:
            continue
        subtotal = item.product.price * item.quantity
        total += subtotal
        lines.append(
            f"{index}. <b>{escape(item.product.title)}</b> x {item.quantity} = {format_price(subtotal, currency)}"
        )

    lines.extend(["", f"<b>Итого:</b> {format_price(total, currency)}"])
    return "\n".join(lines)


def order_text(order, currency: str, include_customer: bool = True) -> str:
    lines = [
        f"<b>Заказ #{order.id}</b>",
        f"<b>Статус:</b> {escape(ORDER_STATUS_LABELS.get(order.status, order.status))}",
        f"<b>Сумма:</b> {format_price(order.total_amount, currency)}",
        f"<b>Создан:</b> {order.created_at.strftime('%Y-%m-%d %H:%M')}",
    ]

    if order.payment_provider:
        lines.append(f"<b>Провайдер оплаты:</b> {escape(order.payment_provider)}")
    if order.payment_status:
        lines.append(f"<b>Статус платежа:</b> {escape(order.payment_status)}")
    if order.external_payment_id:
        lines.append(f"<b>Внешний ID:</b> <code>{escape(order.external_payment_id)}</code>")
    if order.payment_amount is not None and order.payment_currency:
        lines.append(f"<b>Сумма платежа:</b> {format_price(order.payment_amount, order.payment_currency)}")
    if order.payment_network:
        lines.append(f"<b>Сеть:</b> {escape(order.payment_network)}")
    if order.payment_txid:
        lines.append(f"<b>TXID:</b> <code>{escape(order.payment_txid)}</code>")
    if order.paid_at:
        lines.append(f"<b>Оплачен:</b> {order.paid_at.strftime('%Y-%m-%d %H:%M')}")
    if getattr(order, "delivery_sent_at", None):
        lines.append(f"<b>Автовыдача:</b> {order.delivery_sent_at.strftime('%Y-%m-%d %H:%M')}")

    if include_customer:
        username = f"@{order.username}" if order.username else "не указан"
        lines.extend(
            [
                f"<b>Покупатель:</b> {escape(order.customer_name)}",
                f"<b>Контакт:</b> {escape(order.contact)}",
                f"<b>Telegram:</b> {escape(username)} / <code>{order.user_id}</code>",
            ]
        )
        if order.comment:
            lines.append(f"<b>Комментарий:</b> {escape(order.comment)}")

    lines.extend(["", "<b>Состав заказа:</b>"])
    for item in order.items:
        subtotal = item.price * item.quantity
        lines.append(f"- {escape(item.title)} x {item.quantity} = {format_price(subtotal, currency)}")

    return "\n".join(lines)
