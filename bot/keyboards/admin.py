from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.const import ORDER_STATUS_LABELS, STOCK_STATUS_LABELS


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Создать категорию", callback_data="admin:create_category")
    builder.button(text="Добавить товар", callback_data="admin:add_product")
    builder.button(text="Список товаров", callback_data="admin:products")
    builder.button(text="Список заказов", callback_data="admin:orders")
    builder.adjust(1)
    return builder.as_markup()


def category_picker_keyboard(categories, prefix: str, include_empty: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(text=category.title, callback_data=f"{prefix}:{category.id}")
    if include_empty:
        builder.button(text="Без категории", callback_data=f"{prefix}:none")
    builder.adjust(1)
    return builder.as_markup()


def stock_status_keyboard(prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for status, label in STOCK_STATUS_LABELS.items():
        builder.button(text=label, callback_data=f"{prefix}:{status}")
    builder.adjust(1)
    return builder.as_markup()


def yes_no_keyboard(prefix: str, yes_text: str = "Да", no_text: str = "Нет") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=yes_text, callback_data=f"{prefix}:yes")
    builder.button(text=no_text, callback_data=f"{prefix}:no")
    builder.adjust(2)
    return builder.as_markup()


def admin_products_keyboard(products) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in products:
        status = "активен" if product.is_active else "скрыт"
        builder.button(
            text=f"{product.title} [{status}]",
            callback_data=f"admin:product:{product.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def admin_product_actions_keyboard(product_id: int, is_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Редактировать", callback_data=f"admin:edit_menu:{product_id}")
    builder.button(
        text="Скрыть" if is_active else "Показать",
        callback_data=f"admin:toggle_active:{product_id}",
    )
    builder.button(text="Удалить", callback_data=f"admin:delete:{product_id}")
    builder.button(text="К списку товаров", callback_data="admin:products")
    builder.adjust(1)
    return builder.as_markup()


def admin_edit_fields_keyboard(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Название", callback_data=f"admin:edit_field:{product_id}:title")
    builder.button(text="Краткое описание", callback_data=f"admin:edit_field:{product_id}:short_description")
    builder.button(text="Полное описание", callback_data=f"admin:edit_field:{product_id}:full_description")
    builder.button(text="Текст после выдачи", callback_data=f"admin:edit_field:{product_id}:delivery_content")
    builder.button(text="ZIP-пул", callback_data=f"admin:edit_field:{product_id}:delivery_files")
    builder.button(text="Цена", callback_data=f"admin:edit_field:{product_id}:price")
    builder.button(text="SKU", callback_data=f"admin:edit_field:{product_id}:sku")
    builder.button(text="Фото", callback_data=f"admin:edit_field:{product_id}:image")
    builder.button(text="Категория", callback_data=f"admin:edit_field:{product_id}:category")
    builder.button(text="Наличие", callback_data=f"admin:edit_field:{product_id}:stock_status")
    builder.button(text="Назад к товару", callback_data=f"admin:product:{product_id}")
    builder.adjust(1)
    return builder.as_markup()


def confirm_delete_keyboard(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Да, удалить", callback_data=f"admin:delete_confirm:{product_id}")
    builder.button(text="Отмена", callback_data=f"admin:product:{product_id}")
    builder.adjust(1)
    return builder.as_markup()


def admin_orders_keyboard(orders, currency: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in orders:
        label = ORDER_STATUS_LABELS.get(order.status, order.status)
        builder.button(
            text=f"#{order.id} | {label} | {order.total_amount:.2f} {currency}",
            callback_data=f"admin:order:{order.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def admin_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for status, label in ORDER_STATUS_LABELS.items():
        builder.button(text=label, callback_data=f"admin:order_status:{order_id}:{status}")
    builder.button(text="К списку заказов", callback_data="admin:orders")
    builder.adjust(1)
    return builder.as_markup()

