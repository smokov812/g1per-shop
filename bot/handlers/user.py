from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import Config
from bot.const import CART_BUTTON, CATALOG_BUTTON, SKIP_BUTTON, OrderStatus, StockStatus
from bot.db.repositories import CartRepository, CategoryRepository, OrderRepository, PaymentRepository, ProductRepository
from bot.keyboards.admin import admin_order_keyboard
from bot.keyboards.user import (
    cart_keyboard,
    categories_keyboard,
    checkout_confirm_keyboard,
    main_menu_keyboard,
    product_keyboard,
    products_keyboard,
    simple_reply_keyboard,
    skip_cancel_keyboard,
)
from bot.services import BasePaymentService, PaymentContext
from bot.states import CheckoutStates
from bot.texts import cart_text, order_text, product_caption
from bot.validators import ValidationError, validate_optional_text, validate_required_text


async def send_product_message(message: Message, product, currency: str) -> None:
    caption = product_caption(product, currency)
    keyboard = product_keyboard(product)
    if product.image:
        await message.answer_photo(product.image, caption=caption, reply_markup=keyboard)
    else:
        await message.answer(caption, reply_markup=keyboard)



def get_user_router() -> Router:
    router = Router(name="user")

    async def show_categories(target_message: Message, session_maker: async_sessionmaker) -> None:
        async with session_maker() as session:
            categories = await CategoryRepository(session).list_all()

        if not categories:
            await target_message.answer("Категории еще не созданы.")
            return

        await target_message.answer("Выберите категорию:", reply_markup=categories_keyboard(categories))

    async def show_cart(target_message: Message, user_id: int, session_maker: async_sessionmaker, currency: str) -> None:
        async with session_maker() as session:
            items = await CartRepository(session).list_items(user_id)

        await target_message.answer(cart_text(items, currency), reply_markup=cart_keyboard(items))

    @router.message(F.text == CATALOG_BUTTON)
    async def catalog_entry(message: Message, session_maker: async_sessionmaker) -> None:
        await show_categories(message, session_maker)

    @router.callback_query(F.data == "user:categories")
    async def categories_callback(call: CallbackQuery, session_maker: async_sessionmaker) -> None:
        await call.answer()
        await show_categories(call.message, session_maker)

    @router.callback_query(F.data.startswith("user:category:"))
    async def category_products(call: CallbackQuery, session_maker: async_sessionmaker) -> None:
        category_id = int(call.data.rsplit(":", 1)[-1])
        async with session_maker() as session:
            category_repo = CategoryRepository(session)
            product_repo = ProductRepository(session)
            category = await category_repo.get(category_id)
            products = await product_repo.list_by_category(category_id=category_id, only_active=True)

        await call.answer()

        if not category:
            await call.message.answer("Категория не найдена.")
            return

        if not products:
            await call.message.answer(f"В категории <b>{escape(category.title)}</b> пока нет активных товаров.")
            return

        await call.message.answer(
            f"<b>{escape(category.title)}</b>\nВыберите товар:",
            reply_markup=products_keyboard(products),
        )

    @router.callback_query(F.data.startswith("user:product:"))
    async def open_product(call: CallbackQuery, session_maker: async_sessionmaker, config: Config) -> None:
        product_id = int(call.data.rsplit(":", 1)[-1])
        async with session_maker() as session:
            product = await ProductRepository(session).get(product_id)

        await call.answer()

        if not product or not product.is_active:
            await call.message.answer("Товар недоступен.")
            return

        await send_product_message(call.message, product, config.currency)

    @router.callback_query(F.data.startswith("user:add:"))
    async def add_to_cart(call: CallbackQuery, session_maker: async_sessionmaker) -> None:
        product_id = int(call.data.rsplit(":", 1)[-1])
        async with session_maker() as session:
            product = await ProductRepository(session).get(product_id)
            if not product or not product.is_active:
                await call.answer("Товар недоступен.", show_alert=True)
                return
            if product.stock_status == StockStatus.OUT_OF_STOCK.value:
                await call.answer("Товара нет в наличии.", show_alert=True)
                return
            await CartRepository(session).add_item(call.from_user.id, product_id)

        await call.answer("Товар добавлен в корзину.", show_alert=True)

    @router.message(F.text == CART_BUTTON)
    async def cart_entry(message: Message, session_maker: async_sessionmaker, config: Config) -> None:
        await show_cart(message, message.from_user.id, session_maker, config.currency)

    @router.callback_query(F.data == "user:cart")
    async def cart_callback(call: CallbackQuery, session_maker: async_sessionmaker, config: Config) -> None:
        await call.answer()
        await show_cart(call.message, call.from_user.id, session_maker, config.currency)

    @router.callback_query(F.data.startswith("user:cart_remove:"))
    async def remove_cart_item(call: CallbackQuery, session_maker: async_sessionmaker, config: Config) -> None:
        product_id = int(call.data.rsplit(":", 1)[-1])
        async with session_maker() as session:
            cart_repo = CartRepository(session)
            await cart_repo.remove_item(call.from_user.id, product_id)
            items = await cart_repo.list_items(call.from_user.id)

        await call.answer("Позиция удалена.")
        await call.message.answer(cart_text(items, config.currency), reply_markup=cart_keyboard(items))

    @router.callback_query(F.data == "user:cart_clear")
    async def clear_cart(call: CallbackQuery, session_maker: async_sessionmaker, config: Config) -> None:
        async with session_maker() as session:
            await CartRepository(session).clear(call.from_user.id)
        await call.answer("Корзина очищена.")
        await call.message.answer(cart_text([], config.currency))

    @router.callback_query(F.data == "user:checkout")
    async def start_checkout(call: CallbackQuery, state: FSMContext, session_maker: async_sessionmaker) -> None:
        async with session_maker() as session:
            items = await CartRepository(session).list_items(call.from_user.id)

        if not items:
            await call.answer("Корзина пуста.", show_alert=True)
            return

        await state.set_state(CheckoutStates.customer_name)
        await call.answer()
        await call.message.answer("Введите имя покупателя.", reply_markup=simple_reply_keyboard("Отмена"))

    @router.message(CheckoutStates.customer_name, F.text)
    async def checkout_customer_name(message: Message, state: FSMContext) -> None:
        try:
            customer_name = validate_required_text(message.text, "Имя", 120)
        except ValidationError as exc:
            await message.answer(str(exc))
            return

        await state.update_data(customer_name=customer_name)
        await state.set_state(CheckoutStates.contact)
        await message.answer(
            "Укажите контакт для связи: Telegram, @username, email или другой удобный способ.",
            reply_markup=simple_reply_keyboard("Отмена"),
        )

    @router.message(CheckoutStates.contact, F.text)
    async def checkout_contact(message: Message, state: FSMContext) -> None:
        try:
            contact = validate_required_text(message.text, "Контакт", 255)
        except ValidationError as exc:
            await message.answer(str(exc))
            return

        await state.update_data(contact=contact)
        await state.set_state(CheckoutStates.comment)
        await message.answer(
            "Комментарий к заказу. Если не нужен, нажмите «Пропустить».",
            reply_markup=skip_cancel_keyboard(),
        )

    @router.message(CheckoutStates.comment, F.text)
    async def checkout_comment(
        message: Message,
        state: FSMContext,
        session_maker: async_sessionmaker,
        config: Config,
        payment_service: BasePaymentService,
    ) -> None:
        try:
            comment = None if message.text == SKIP_BUTTON else validate_optional_text(message.text, "Комментарий", 500)
        except ValidationError as exc:
            await message.answer(str(exc))
            return

        await state.update_data(comment=comment)

        async with session_maker() as session:
            items = await CartRepository(session).list_items(message.from_user.id)

        if not items:
            await state.clear()
            await message.answer(
                "Корзина стала пустой. Оформление остановлено.",
                reply_markup=main_menu_keyboard(is_admin=message.from_user.id == config.admin_id),
            )
            return

        summary = cart_text(items, config.currency)
        data = await state.get_data()
        text = (
            "<b>Проверьте заказ</b>\n\n"
            f"{summary}\n\n"
            f"<b>Имя:</b> {escape(data['customer_name'])}\n"
            f"<b>Контакт:</b> {escape(data['contact'])}\n"
            f"<b>Комментарий:</b> {escape(comment) if comment else 'без комментария'}\n\n"
            f"{payment_service.checkout_hint()}"
        )
        await state.set_state(CheckoutStates.confirm)
        await message.answer(text, reply_markup=checkout_confirm_keyboard())

    @router.callback_query(F.data == "user:checkout_cancel")
    async def cancel_checkout(call: CallbackQuery, state: FSMContext, config: Config) -> None:
        await state.clear()
        await call.answer("Оформление отменено.")
        await call.message.answer(
            "Заказ не создан.",
            reply_markup=main_menu_keyboard(is_admin=call.from_user.id == config.admin_id),
        )

    @router.callback_query(CheckoutStates.confirm, F.data == "user:checkout_confirm")
    async def confirm_checkout(
        call: CallbackQuery,
        state: FSMContext,
        session_maker: async_sessionmaker,
        config: Config,
        bot: Bot,
        payment_service: BasePaymentService,
    ) -> None:
        data = await state.get_data()
        instructions = None

        async with session_maker() as session:
            cart_repo = CartRepository(session)
            order_repo = OrderRepository(session)
            payment_repo = PaymentRepository(session)
            items = await cart_repo.list_items(call.from_user.id)
            if not items:
                await state.clear()
                await call.answer("Корзина пуста.", show_alert=True)
                return

            order = await order_repo.create_from_cart(
                user_id=call.from_user.id,
                username=call.from_user.username,
                customer_name=data["customer_name"],
                contact=data["contact"],
                comment=data.get("comment"),
                cart_items=items,
            )

            payment_error = None
            try:
                instructions = await payment_service.create_payment(
                    PaymentContext(
                        order_id=order.id,
                        amount=order.total_amount,
                        currency=config.currency,
                        user_id=order.user_id,
                        customer_name=order.customer_name,
                    )
                )
            except Exception as exc:
                payment_error = str(exc)

            if instructions:
                order = await order_repo.update_payment_metadata(
                    order.id,
                    provider=instructions.provider,
                    external_payment_id=instructions.external_id,
                    payment_url=instructions.payment_url,
                    payment_status=instructions.payment_status,
                    payment_currency=instructions.payment_currency,
                    payment_network=instructions.payment_network,
                    payment_amount=instructions.payment_amount,
                ) or order
                await payment_repo.register_checkout_payment(
                    order_id=order.id,
                    provider=instructions.provider,
                    external_payment_id=instructions.external_id,
                    status=instructions.payment_status,
                    amount=instructions.payment_amount,
                    currency=instructions.payment_currency,
                    network=instructions.payment_network,
                    payment_url=instructions.payment_url,
                )
                target_status = OrderStatus.AWAITING_PAYMENT.value if instructions.provider == "cryptomus" else OrderStatus.NEW.value
                updated_order = await order_repo.update_status(order.id, target_status)
                if updated_order:
                    order = updated_order
            else:
                await payment_repo.register_checkout_payment(
                    order_id=order.id,
                    provider=payment_service.provider_code,
                    status="error",
                    amount=order.total_amount,
                    currency=config.currency,
                    last_error=payment_error,
                )

        await state.clear()
        await call.answer("Заказ оформлен.", show_alert=True)

        if instructions:
            user_text = instructions.text
        else:
            user_text = (
                f"<b>Заказ #{order.id} создан.</b>\n\n"
                "Не удалось автоматически подготовить инструкцию по оплате. "
                "Админ получит заказ и свяжется с вами вручную."
            )

        await call.message.answer(user_text, reply_markup=main_menu_keyboard(is_admin=call.from_user.id == config.admin_id))

        admin_text = order_text(order, config.currency, include_customer=True)
        if payment_error:
            admin_text += f"\n<b>Ошибка подготовки платежа:</b> {escape(payment_error)}"

        await bot.send_message(config.admin_id, admin_text, reply_markup=admin_order_keyboard(order.id))

    return router
