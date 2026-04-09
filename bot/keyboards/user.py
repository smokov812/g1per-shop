from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from bot.const import (
    ADMIN_PANEL_BUTTON,
    CANCEL_BUTTON,
    CART_BUTTON,
    CATALOG_BUTTON,
    PAYMENT_PROVIDER_LABELS,
    SERVICE_BACK_BUTTON,
    SERVICE_BUTTON,
    SERVICE_CHANNEL_BUTTON,
    SERVICE_OFFER_BUTTON,
    SERVICE_PRIVACY_BUTTON,
    SERVICE_SUPPORT_BUTTON,
    SERVICE_TERMS_BUTTON,
    SKIP_BUTTON,
)


USER_PAYMENT_LABELS = {
    "manual_crypto": "💸 Ручная крипто-оплата",
    "cryptomus": "🪙 Cryptomus",
    "lzt_market": "🛒 LOLZ Market",
}

CUSTOM_BUTTON_EMOJI_ID = "5472055112702629499"


def _reply_button(text: str, *, icon_custom_emoji_id: str | None = None, style: str | None = None) -> KeyboardButton:
    return KeyboardButton(
        text=text,
        icon_custom_emoji_id=icon_custom_emoji_id,
        style=style,
    )


def main_menu_keyboard(is_admin: bool = False, has_service: bool = False) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        _reply_button(CATALOG_BUTTON, style="success"),
        _reply_button(CART_BUTTON, style="primary"),
    )
    if has_service:
        builder.row(
            _reply_button(
                SERVICE_BUTTON,
                icon_custom_emoji_id=CUSTOM_BUTTON_EMOJI_ID,
                style="primary",
            )
        )
    if is_admin:
        builder.row(_reply_button(ADMIN_PANEL_BUTTON, style="danger"))
    return builder.as_markup(resize_keyboard=True)



def service_menu_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(_reply_button(SERVICE_OFFER_BUTTON))
    builder.row(_reply_button(SERVICE_PRIVACY_BUTTON))
    builder.row(_reply_button(SERVICE_TERMS_BUTTON))
    builder.row(_reply_button(SERVICE_CHANNEL_BUTTON))
    builder.row(
        _reply_button(
            SERVICE_SUPPORT_BUTTON,
            icon_custom_emoji_id=CUSTOM_BUTTON_EMOJI_ID,
            style="primary",
        )
    )
    builder.row(_reply_button(SERVICE_BACK_BUTTON, style="danger"))
    return builder.as_markup(resize_keyboard=True)



def simple_reply_keyboard(*buttons: str) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    for button in buttons:
        if button == CANCEL_BUTTON:
            builder.row(_reply_button(button, style="danger"))
        elif button == SKIP_BUTTON:
            builder.row(_reply_button(button, style="primary"))
        else:
            builder.row(_reply_button(button))
    return builder.as_markup(resize_keyboard=True)



def skip_cancel_keyboard() -> ReplyKeyboardMarkup:
    return simple_reply_keyboard(SKIP_BUTTON, CANCEL_BUTTON)



def categories_keyboard(categories) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(text=f"📂 {category.title}", callback_data=f"user:category:{category.id}")
    builder.adjust(1)
    return builder.as_markup()



def products_keyboard(products) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in products:
        builder.button(text=product.title, callback_data=f"user:product:{product.id}")
    builder.button(text="⬅️ К категориям", callback_data="user:categories")
    builder.adjust(1)
    return builder.as_markup()



def product_keyboard(product) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if product.stock_status != "out_of_stock" and product.is_active:
        builder.button(text="🛒 Добавить в корзину", callback_data=f"user:add:{product.id}")
    builder.button(text="🧺 Открыть корзину", callback_data="user:cart")
    if product.category_id:
        builder.button(text="⬅️ Назад к товарам", callback_data=f"user:category:{product.category_id}")
    else:
        builder.button(text="⬅️ К категориям", callback_data="user:categories")
    builder.adjust(1)
    return builder.as_markup()



def cart_keyboard(items) -> InlineKeyboardMarkup | None:
    if not items:
        return None

    builder = InlineKeyboardBuilder()
    for item in items:
        if item.product:
            builder.button(
                text=f"🗑️ Удалить {item.product.title}",
                callback_data=f"user:cart_remove:{item.product.id}",
            )
    builder.button(text="🧹 Очистить корзину", callback_data="user:cart_clear")
    builder.button(text="✅ Оформить заказ", callback_data="user:checkout")
    builder.button(text="⬅️ Продолжить покупки", callback_data="user:categories")
    builder.adjust(1)
    return builder.as_markup()



def payment_methods_keyboard(provider_codes: tuple[str, ...]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for provider_code in provider_codes:
        builder.button(
            text=USER_PAYMENT_LABELS.get(provider_code, PAYMENT_PROVIDER_LABELS.get(provider_code, provider_code)),
            callback_data=f"user:checkout_provider:{provider_code}",
        )
    builder.button(text="❌ Отменить", callback_data="user:checkout_cancel")
    builder.adjust(1)
    return builder.as_markup()



def checkout_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить заказ", callback_data="user:checkout_confirm")
    builder.button(text="❌ Отменить", callback_data="user:checkout_cancel")
    builder.adjust(1)
    return builder.as_markup()
