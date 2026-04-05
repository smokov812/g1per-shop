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
    "price": "цену",
    "sku": "SKU",
}
