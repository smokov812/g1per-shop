from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


class ValidationError(ValueError):
    pass


SKU_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def validate_required_text(value: str, field_name: str, max_length: int, min_length: int = 1) -> str:
    cleaned = (value or "").strip()
    if len(cleaned) < min_length:
        raise ValidationError(f"Поле «{field_name}» не может быть пустым.")
    if len(cleaned) > max_length:
        raise ValidationError(f"Поле «{field_name}» слишком длинное. Максимум {max_length} символов.")
    return cleaned


def validate_optional_text(value: str, field_name: str, max_length: int) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    if len(cleaned) > max_length:
        raise ValidationError(f"Поле «{field_name}» слишком длинное. Максимум {max_length} символов.")
    return cleaned


def validate_sku(value: str) -> str:
    cleaned = validate_required_text(value, "SKU", 120)
    if not SKU_PATTERN.fullmatch(cleaned):
        raise ValidationError("SKU может содержать только латиницу, цифры, дефис и подчеркивание.")
    return cleaned


def validate_price(value: str) -> Decimal:
    try:
        price = Decimal(value.replace(",", ".").strip())
    except (InvalidOperation, AttributeError):
        raise ValidationError("Не удалось распознать цену. Пример: 19.99")
    if price <= 0:
        raise ValidationError("Цена должна быть больше нуля.")
    return price
