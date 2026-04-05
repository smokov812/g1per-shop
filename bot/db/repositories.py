from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.const import OrderStatus
from bot.db.models import (
    AdminAuditLog,
    CartItem,
    Category,
    Order,
    OrderItem,
    Payment,
    PaymentEvent,
    Product,
    RequestRateLimit,
)


@dataclass(slots=True)
class PaymentProcessResult:
    duplicate: bool
    order: Order | None
    payment: Payment | None
    applied: bool
    previous_status: str | None
    current_status: str | None


@dataclass(slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after: float


class CategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[Category]:
        result = await self.session.execute(select(Category).order_by(Category.title))
        return list(result.scalars().all())

    async def get(self, category_id: int) -> Category | None:
        result = await self.session.execute(select(Category).where(Category.id == category_id))
        return result.scalar_one_or_none()

    async def create(self, title: str, description: str | None) -> Category | None:
        category = Category(title=title.strip(), description=description or None)
        self.session.add(category)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return None
        await self.session.refresh(category)
        return category


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_category(self, category_id: int, only_active: bool = True) -> list[Product]:
        statement = (
            select(Product)
            .options(selectinload(Product.category))
            .where(Product.category_id == category_id)
            .order_by(Product.created_at.desc())
        )
        if only_active:
            statement = statement.where(Product.is_active.is_(True))

        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_all(self) -> list[Product]:
        result = await self.session.execute(
            select(Product).options(selectinload(Product.category)).order_by(Product.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, product_id: int) -> Product | None:
        result = await self.session.execute(
            select(Product).options(selectinload(Product.category)).where(Product.id == product_id)
        )
        return result.scalar_one_or_none()

    async def get_by_sku(self, sku: str) -> Product | None:
        result = await self.session.execute(select(Product).where(Product.sku == sku))
        return result.scalar_one_or_none()

    async def create(self, **fields) -> Product | None:
        product = Product(**fields)
        self.session.add(product)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return None
        await self.session.refresh(product)
        return await self.get(product.id)

    async def update(self, product_id: int, **fields) -> Product | None:
        product = await self.get(product_id)
        if not product:
            return None

        for key, value in fields.items():
            setattr(product, key, value)

        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return None

        await self.session.refresh(product)
        return await self.get(product.id)

    async def delete(self, product_id: int) -> bool:
        product = await self.get(product_id)
        if not product:
            return False

        await self.session.delete(product)
        await self.session.commit()
        return True


class CartRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_items(self, user_id: int) -> list[CartItem]:
        result = await self.session.execute(
            select(CartItem)
            .options(selectinload(CartItem.product).selectinload(Product.category))
            .where(CartItem.user_id == user_id)
            .order_by(CartItem.created_at.asc())
        )
        return list(result.scalars().all())

    async def add_item(self, user_id: int, product_id: int, quantity: int = 1) -> None:
        result = await self.session.execute(
            select(CartItem).where(CartItem.user_id == user_id, CartItem.product_id == product_id)
        )
        item = result.scalar_one_or_none()

        if item:
            item.quantity += quantity
        else:
            self.session.add(CartItem(user_id=user_id, product_id=product_id, quantity=quantity))

        await self.session.commit()

    async def remove_item(self, user_id: int, product_id: int) -> bool:
        result = await self.session.execute(
            select(CartItem).where(CartItem.user_id == user_id, CartItem.product_id == product_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            return False

        await self.session.delete(item)
        await self.session.commit()
        return True

    async def clear(self, user_id: int) -> None:
        await self.session.execute(delete(CartItem).where(CartItem.user_id == user_id))
        await self.session.commit()

    async def total(self, user_id: int) -> Decimal:
        items = await self.list_items(user_id)
        total = Decimal("0")
        for item in items:
            if item.product:
                total += item.product.price * item.quantity
        return total


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_recent(self, limit: int = 20) -> list[Order]:
        result = await self.session.execute(
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.payment_events), selectinload(Order.payments))
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get(self, order_id: int) -> Order | None:
        result = await self.session.execute(
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.payment_events), selectinload(Order.payments))
            .where(Order.id == order_id)
        )
        return result.scalar_one_or_none()

    async def create_from_cart(
        self,
        *,
        user_id: int,
        username: str | None,
        customer_name: str,
        contact: str,
        comment: str | None,
        cart_items: list[CartItem],
    ) -> Order:
        total = Decimal("0")

        for item in cart_items:
            if item.product:
                total += item.product.price * item.quantity

        order = Order(
            user_id=user_id,
            username=username,
            customer_name=customer_name,
            contact=contact,
            comment=comment,
            total_amount=total,
            status=OrderStatus.NEW.value,
        )
        self.session.add(order)
        await self.session.flush()

        for item in cart_items:
            if not item.product:
                continue

            self.session.add(
                OrderItem(
                    order_id=order.id,
                    product_id=item.product.id,
                    title=item.product.title,
                    sku=item.product.sku,
                    price=item.product.price,
                    quantity=item.quantity,
                )
            )
            await self.session.delete(item)

        await self.session.commit()
        return await self.get(order.id)

    async def update_status(self, order_id: int, status: str) -> Order | None:
        order = await self.get(order_id)
        if not order:
            return None

        order.status = status
        await self.session.commit()
        await self.session.refresh(order)
        return await self.get(order.id)

    async def update_payment_metadata(
        self,
        order_id: int,
        *,
        provider: str,
        external_payment_id: str | None = None,
        payment_url: str | None = None,
        payment_status: str | None = None,
        payment_currency: str | None = None,
        payment_network: str | None = None,
        payment_amount: Decimal | None = None,
        payment_txid: str | None = None,
    ) -> Order | None:
        order = await self.get(order_id)
        if not order:
            return None

        order.payment_provider = provider
        if external_payment_id:
            order.external_payment_id = external_payment_id
        if payment_url:
            order.payment_url = payment_url
        if payment_status:
            order.payment_status = payment_status
        if payment_currency:
            order.payment_currency = payment_currency
        if payment_network:
            order.payment_network = payment_network
        if payment_amount is not None:
            order.payment_amount = payment_amount
        if payment_txid:
            order.payment_txid = payment_txid

        await self.session.commit()
        await self.session.refresh(order)
        return await self.get(order.id)


class PaymentRepository:
    PENDING_STATUSES = {"new", "check", "confirm_check", "wrong_amount_waiting", "process", "pending", "awaiting_payment"}
    FINAL_STATUSES = {"paid", "paid_over", "cancel", "fail", "system_fail"}

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, payment_id: int) -> Payment | None:
        result = await self.session.execute(
            select(Payment).options(selectinload(Payment.order)).where(Payment.id == payment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_provider_and_external_id(self, provider: str, external_payment_id: str) -> Payment | None:
        result = await self.session.execute(
            select(Payment)
            .options(selectinload(Payment.order))
            .where(Payment.provider == provider, Payment.external_payment_id == external_payment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_order(self, order_id: int, provider: str) -> Payment | None:
        result = await self.session.execute(
            select(Payment)
            .options(selectinload(Payment.order))
            .where(Payment.order_id == order_id, Payment.provider == provider)
            .order_by(Payment.created_at.desc())
        )
        return result.scalars().first()

    async def register_checkout_payment(
        self,
        *,
        order_id: int,
        provider: str,
        external_payment_id: str | None = None,
        status: str | None = None,
        amount: Decimal | None = None,
        currency: str | None = None,
        network: str | None = None,
        payment_url: str | None = None,
        last_error: str | None = None,
    ) -> Payment:
        payment = None
        if external_payment_id:
            payment = await self.get_by_provider_and_external_id(provider, external_payment_id)
        if payment is None:
            payment = await self.get_by_order(order_id, provider)

        now = datetime.utcnow()
        if payment is None:
            payment = Payment(
                order_id=order_id,
                provider=provider,
                external_payment_id=external_payment_id,
                status=status or "new",
                amount=amount,
                currency=currency,
                network=network,
                payment_url=payment_url,
                last_error=last_error,
                last_checked_at=now,
            )
            self.session.add(payment)
        else:
            payment.external_payment_id = external_payment_id or payment.external_payment_id
            payment.status = status or payment.status
            payment.amount = amount if amount is not None else payment.amount
            payment.currency = currency or payment.currency
            payment.network = network or payment.network
            payment.payment_url = payment_url or payment.payment_url
            payment.last_error = last_error
            payment.last_checked_at = now

        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def list_stale_pending(
        self,
        *,
        provider: str,
        stale_after_seconds: int,
        limit: int = 20,
    ) -> list[Payment]:
        cutoff = datetime.utcnow() - timedelta(seconds=stale_after_seconds)
        statement = (
            select(Payment)
            .options(selectinload(Payment.order))
            .join(Order, Payment.order_id == Order.id)
            .where(
                Payment.provider == provider,
                Payment.status.in_(tuple(self.PENDING_STATUSES)),
                Order.status.in_((OrderStatus.NEW.value, OrderStatus.AWAITING_PAYMENT.value)),
            )
            .where((Payment.last_checked_at.is_(None)) | (Payment.last_checked_at <= cutoff))
            .order_by(Payment.last_checked_at.asc().nullsfirst(), Payment.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def mark_sync_error(self, payment_id: int, error: str) -> None:
        payment = await self.get(payment_id)
        if not payment:
            return

        payment.last_error = error[:2000]
        payment.last_checked_at = datetime.utcnow()
        await self.session.commit()

    async def process_cryptomus_callback(
        self,
        payload: dict,
        *,
        source: str,
        source_ip: str | None = None,
    ) -> PaymentProcessResult:
        payload_hash = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()

        existing = await self.session.execute(select(PaymentEvent).where(PaymentEvent.event_hash == payload_hash))
        existing_event = existing.scalar_one_or_none()
        if existing_event:
            order = await OrderRepository(self.session).get(existing_event.order_id) if existing_event.order_id else None
            payment = await self.get(existing_event.payment_id) if existing_event.payment_id else None
            return PaymentProcessResult(
                duplicate=True,
                order=order,
                payment=payment,
                applied=False,
                previous_status=order.status if order else None,
                current_status=order.status if order else None,
            )

        order_id = _parse_order_id(payload.get("order_id"))
        external_payment_id = _optional_string(payload.get("uuid"))
        order = await OrderRepository(self.session).get(order_id) if order_id else None
        payment = None
        if external_payment_id:
            payment = await self.get_by_provider_and_external_id("cryptomus", external_payment_id)
        if payment is None and order_id:
            payment = await self.get_by_order(order_id, "cryptomus")

        if payment is None and order is not None:
            payment = Payment(order_id=order.id, provider="cryptomus")
            self.session.add(payment)
            await self.session.flush()

        status = _optional_string(payload.get("status")) or "check"
        is_final = _coerce_bool(payload.get("is_final"))
        previous_status = order.status if order else None
        now = datetime.utcnow()

        if payment is not None:
            payment.external_payment_id = external_payment_id or payment.external_payment_id
            payment.status = status
            payment.payment_url = _optional_string(payload.get("url")) or payment.payment_url
            payment.currency = _optional_string(payload.get("payer_currency")) or _optional_string(payload.get("currency")) or payment.currency
            payment.network = _optional_string(payload.get("network")) or payment.network
            payment.txid = _optional_string(payload.get("txid")) or payment.txid
            payment.last_error = None
            payment.last_checked_at = now

            amount_value = payload.get("payer_amount") or payload.get("amount")
            parsed_amount = _parse_decimal(amount_value)
            if parsed_amount is not None:
                payment.amount = parsed_amount

        event = PaymentEvent(
            order_id=order.id if order else None,
            payment_id=payment.id if payment else None,
            provider="cryptomus",
            source=source,
            event_hash=payload_hash,
            external_payment_id=external_payment_id,
            status=status,
            is_final=is_final,
            txid=_optional_string(payload.get("txid")),
            source_ip=source_ip,
            payload_json=json.dumps(payload, ensure_ascii=False),
        )
        self.session.add(event)

        current_status = previous_status
        if order:
            order.payment_provider = "cryptomus"
            order.external_payment_id = external_payment_id or order.external_payment_id
            order.payment_url = _optional_string(payload.get("url")) or order.payment_url
            order.payment_status = status or order.payment_status
            order.payment_currency = _optional_string(payload.get("payer_currency")) or _optional_string(payload.get("currency")) or order.payment_currency
            order.payment_network = _optional_string(payload.get("network")) or order.payment_network
            order.payment_txid = _optional_string(payload.get("txid")) or order.payment_txid

            parsed_amount = _parse_decimal(payload.get("payer_amount") or payload.get("amount"))
            if parsed_amount is not None:
                order.payment_amount = parsed_amount

            mapped_status = _map_cryptomus_status(status, is_final, order.status)
            if mapped_status and mapped_status != order.status:
                order.status = mapped_status
                current_status = mapped_status
                if mapped_status == OrderStatus.PAID.value:
                    order.paid_at = now
            else:
                current_status = order.status

        if payment and current_status == OrderStatus.PAID.value and payment.paid_at is None:
            payment.paid_at = now

        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            order = await OrderRepository(self.session).get(order_id) if order_id else None
            payment = await self.get_by_provider_and_external_id("cryptomus", external_payment_id) if external_payment_id else None
            return PaymentProcessResult(
                duplicate=True,
                order=order,
                payment=payment,
                applied=False,
                previous_status=order.status if order else None,
                current_status=order.status if order else None,
            )

        if payment:
            await self.session.refresh(payment)
            payment = await self.get(payment.id)
        if order:
            order = await OrderRepository(self.session).get(order.id)

        return PaymentProcessResult(
            duplicate=False,
            order=order,
            payment=payment,
            applied=order is not None,
            previous_status=previous_status,
            current_status=current_status,
        )


class AdminAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log(
        self,
        *,
        admin_id: int,
        action: str,
        entity_type: str,
        entity_id: str | int | None = None,
        payload: dict | None = None,
    ) -> AdminAuditLog:
        entry = AdminAuditLog(
            admin_id=admin_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            payload_json=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry


class RateLimitRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def consume(self, *, user_id: int, scope: str, window_seconds: float) -> RateLimitDecision:
        now = datetime.utcnow()
        result = await self.session.execute(
            select(RequestRateLimit).where(RequestRateLimit.user_id == user_id, RequestRateLimit.scope == scope)
        )
        record = result.scalar_one_or_none()

        if record:
            elapsed = (now - record.last_hit_at).total_seconds()
            if elapsed < window_seconds:
                await self.session.rollback()
                return RateLimitDecision(allowed=False, retry_after=max(0.0, window_seconds - elapsed))
            record.last_hit_at = now
        else:
            self.session.add(RequestRateLimit(user_id=user_id, scope=scope, last_hit_at=now))

        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return RateLimitDecision(allowed=False, retry_after=window_seconds)

        return RateLimitDecision(allowed=True, retry_after=0.0)


def _map_cryptomus_status(status: str, is_final: bool, current_order_status: str | None) -> str | None:
    normalized = (status or "").lower().strip()

    if normalized in {"paid", "paid_over"} and is_final:
        return OrderStatus.PAID.value
    if normalized in {"confirm_check", "wrong_amount_waiting", "check", "process"}:
        return OrderStatus.AWAITING_PAYMENT.value
    if normalized in {"cancel", "fail", "system_fail"} and is_final:
        if current_order_status not in {OrderStatus.PAID.value, OrderStatus.COMPLETED.value}:
            return OrderStatus.CANCELED.value
    return None


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _parse_decimal(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _optional_string(value) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _parse_order_id(value) -> int | None:
    raw = _optional_string(value)
    if raw and raw.isdigit():
        return int(raw)
    return None

