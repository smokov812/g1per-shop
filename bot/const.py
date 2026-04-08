from __future__ import annotations

from enum import Enum


class StockStatus(str, Enum):
    IN_STOCK = "in_stock"
    PREORDER = "preorder"
    OUT_OF_STOCK = "out_of_stock"


class OrderStatus(str, Enum):
    NEW = "new"
    AWAITING_PAYMENT = "awaiting_payment"
    PAID = "paid"
    COMPLETED = "completed"
    CANCELED = "canceled"


MAIN_MENU_BUTTON = "Главное меню"
CATALOG_BUTTON = "Каталог"
CART_BUTTON = "Корзина"
SERVICE_BUTTON = "О сервисе"
SERVICE_OFFER_BUTTON = "Оферта"
SERVICE_PRIVACY_BUTTON = "Политика конфиденциальности"
SERVICE_TERMS_BUTTON = "Пользовательское соглашение"
SERVICE_CHANNEL_BUTTON = "Новостной канал"
SERVICE_SUPPORT_BUTTON = "Тех. поддержка"
SERVICE_BACK_BUTTON = "Назад"
SUPPORT_BUTTON = "Поддержка"
ADMIN_PANEL_BUTTON = "Админ-панель"
SKIP_BUTTON = "Пропустить"
CANCEL_BUTTON = "Отмена"
REMOVE_PHOTO_BUTTON = "Удалить фото"

PAYMENT_PROVIDER_LABELS = {
    "manual_crypto": "Ручная крипто-оплата",
    "cryptomus": "Cryptomus",
    "lzt_market": "LOLZ Market",
}

STOCK_STATUS_LABELS = {
    StockStatus.IN_STOCK.value: "В наличии",
    StockStatus.PREORDER.value: "Под заказ",
    StockStatus.OUT_OF_STOCK.value: "Нет в наличии",
}

ORDER_STATUS_LABELS = {
    OrderStatus.NEW.value: "Новый",
    OrderStatus.AWAITING_PAYMENT.value: "Ожидает оплату",
    OrderStatus.PAID.value: "Оплачен",
    OrderStatus.COMPLETED.value: "Завершен",
    OrderStatus.CANCELED.value: "Отменен",
}

TEXT_PRODUCT_FIELDS = {
    "title": "название",
    "short_description": "краткое описание",
    "full_description": "полное описание",
    "delivery_content": "текст после выдачи",
    "post_payment_message": "инструкцию после оплаты",
    "price": "цену",
    "sku": "SKU",
}


def button_matches(text: str | None, label: str) -> bool:
    value = (text or "").strip()
    return value == label or value.endswith(f" {label}")
