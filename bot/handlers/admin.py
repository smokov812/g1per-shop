from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import Config
from bot.const import (
    ADMIN_PANEL_BUTTON,
    CANCEL_BUTTON,
    ORDER_STATUS_LABELS,
    REMOVE_PHOTO_BUTTON,
    SKIP_BUTTON,
    TEXT_PRODUCT_FIELDS,
)
from bot.db.repositories import AdminAuditLogRepository, CategoryRepository, DeliveryFileRepository, OrderRepository, ProductRepository
from bot.filters import AdminFilter
from bot.keyboards.admin import (
    admin_categories_keyboard,
    admin_category_actions_keyboard,
    admin_edit_fields_keyboard,
    admin_menu_keyboard,
    admin_order_keyboard,
    admin_orders_keyboard,
    admin_product_actions_keyboard,
    admin_products_keyboard,
    category_picker_keyboard,
    confirm_delete_keyboard,
    stock_status_keyboard,
    yes_no_keyboard,
)
from bot.keyboards.user import main_menu_keyboard, simple_reply_keyboard, skip_cancel_keyboard
from bot.services import deliver_order_digital_content
from bot.states import CreateCategoryStates, CreateProductStates, EditCategoryStates, EditProductStates, ManualOrderDeliveryStates
from bot.texts import admin_product_caption, order_text
from bot.validators import ValidationError, validate_optional_text, validate_price, validate_required_text, validate_sku


async def log_admin_action(
    session_maker: async_sessionmaker,
    *,
    admin_id: int,
    action: str,
    entity_type: str,
    entity_id: str | int | None = None,
    payload: dict | None = None,
) -> None:
    async with session_maker() as session:
        await AdminAuditLogRepository(session).log(
            admin_id=admin_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )



def get_admin_router(admin_id: int) -> Router:
    router = Router(name="admin")
    admin_filter = AdminFilter(admin_id)
    router.message.filter(admin_filter)
    router.callback_query.filter(admin_filter)

    async def show_admin_panel(message: Message) -> None:
        await message.answer("Админ-панель:", reply_markup=admin_menu_keyboard())

    async def show_categories(target_message: Message, session_maker: async_sessionmaker) -> None:
        async with session_maker() as session:
            categories = await CategoryRepository(session).list_all()

        if not categories:
            await target_message.answer("Категории еще не созданы.")
            return

        await target_message.answer("Список категорий:", reply_markup=admin_categories_keyboard(categories))

    async def show_products(target_message: Message, session_maker: async_sessionmaker) -> None:
        async with session_maker() as session:
            products = await ProductRepository(session).list_all()

        if not products:
            await target_message.answer("Товары еще не добавлены.")
            return

        await target_message.answer("Список товаров:", reply_markup=admin_products_keyboard(products))

    async def show_orders(target_message: Message, session_maker: async_sessionmaker, currency: str) -> None:
        async with session_maker() as session:
            orders = await OrderRepository(session).list_recent()

        if not orders:
            await target_message.answer("Заказов пока нет.")
            return

        await target_message.answer("Последние заказы:", reply_markup=admin_orders_keyboard(orders, currency))

    @router.message(Command("admin"))
    @router.message(F.text == ADMIN_PANEL_BUTTON)
    async def admin_panel_entry(message: Message) -> None:
        await show_admin_panel(message)

    @router.callback_query(F.data == "admin:menu")
    async def admin_panel_callback(call: CallbackQuery) -> None:
        await call.answer()
        await show_admin_panel(call.message)

    @router.message(Command("products"))
    async def admin_products_command(message: Message, session_maker: async_sessionmaker) -> None:
        await show_products(message, session_maker)

    @router.message(Command("orders"))
    async def admin_orders_command(message: Message, session_maker: async_sessionmaker, config: Config) -> None:
        await show_orders(message, session_maker, config.currency)

    @router.callback_query(F.data == "admin:categories")
    async def admin_categories_callback(call: CallbackQuery, session_maker: async_sessionmaker) -> None:
        await call.answer()
        await show_categories(call.message, session_maker)

    @router.callback_query(F.data == "admin:products")
    async def admin_products_callback(call: CallbackQuery, session_maker: async_sessionmaker) -> None:
        await call.answer()
        await show_products(call.message, session_maker)

    @router.callback_query(F.data == "admin:orders")
    async def admin_orders_callback(call: CallbackQuery, session_maker: async_sessionmaker, config: Config) -> None:
        await call.answer()
        await show_orders(call.message, session_maker, config.currency)

    @router.callback_query(F.data == "admin:create_category")
    async def create_category_start(call: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await state.set_state(CreateCategoryStates.title)
        await call.answer()
        await call.message.answer("Введите название категории.", reply_markup=simple_reply_keyboard(CANCEL_BUTTON))

    @router.message(CreateCategoryStates.title, F.text)
    async def create_category_title(message: Message, state: FSMContext) -> None:
        try:
            title = validate_required_text(message.text, "Название категории", 120)
        except ValidationError as exc:
            await message.answer(str(exc))
            return

        await state.update_data(title=title)
        await state.set_state(CreateCategoryStates.description)
        await message.answer("Введите описание категории или нажмите «Пропустить».", reply_markup=skip_cancel_keyboard())

    @router.message(CreateCategoryStates.description, F.text)
    async def create_category_description(message: Message, state: FSMContext, session_maker: async_sessionmaker, config: Config) -> None:
        try:
            description = None if message.text == SKIP_BUTTON else validate_optional_text(message.text, "Описание категории", 500)
        except ValidationError as exc:
            await message.answer(str(exc))
            return

        data = await state.get_data()
        async with session_maker() as session:
            category = await CategoryRepository(session).create(data["title"], description)

        if not category:
            await message.answer("Категория с таким названием уже существует.")
            return

        await log_admin_action(
            session_maker,
            admin_id=message.from_user.id,
            action="category_create",
            entity_type="category",
            entity_id=category.id,
            payload={"title": category.title, "description": category.description},
        )

        await state.clear()
        await message.answer(
            f"Категория <b>{escape(category.title)}</b> создана.",
            reply_markup=main_menu_keyboard(is_admin=message.from_user.id == config.admin_id),
        )
        await show_admin_panel(message)

    @router.callback_query(F.data.startswith("admin:category:"))
    async def open_admin_category(call: CallbackQuery, session_maker: async_sessionmaker) -> None:
        category_id = int(call.data.rsplit(":", 1)[-1])
        async with session_maker() as session:
            category = await CategoryRepository(session).get(category_id)
            products = await ProductRepository(session).list_by_category(category_id, only_active=False)

        await call.answer()
        if not category:
            await call.message.answer("Категория не найдена.")
            return

        description = escape(category.description) if category.description else "без описания"
        text = (
            f"<b>Категория #{category.id}</b>\n"
            f"<b>Название:</b> {escape(category.title)}\n"
            f"<b>Описание:</b> {description}\n"
            f"<b>Товаров:</b> {len(products)}"
        )
        await call.message.answer(text, reply_markup=admin_category_actions_keyboard(category.id))

    @router.callback_query(F.data.startswith("admin:category_rename:"))
    async def rename_category_start(call: CallbackQuery, state: FSMContext) -> None:
        category_id = int(call.data.rsplit(":", 1)[-1])
        await state.clear()
        await state.set_state(EditCategoryStates.title)
        await state.update_data(category_id=category_id)
        await call.answer()
        await call.message.answer("Введите новое название категории.", reply_markup=simple_reply_keyboard(CANCEL_BUTTON))

    @router.message(EditCategoryStates.title, F.text)
    async def rename_category_finish(message: Message, state: FSMContext, session_maker: async_sessionmaker, config: Config) -> None:
        data = await state.get_data()
        try:
            title = validate_required_text(message.text, "Название категории", 120)
        except ValidationError as exc:
            await message.answer(str(exc))
            return

        async with session_maker() as session:
            category = await CategoryRepository(session).update(data["category_id"], title=title)

        if not category:
            await message.answer("Не удалось обновить категорию. Возможно, такое название уже занято.")
            return

        await log_admin_action(
            session_maker,
            admin_id=message.from_user.id,
            action="category_update",
            entity_type="category",
            entity_id=category.id,
            payload={"title": category.title},
        )

        await state.clear()
        await message.answer(
            f"Категория <b>{escape(category.title)}</b> обновлена.",
            reply_markup=main_menu_keyboard(is_admin=message.from_user.id == config.admin_id),
        )
        await show_categories(message, session_maker)

    @router.callback_query(F.data.startswith("admin:category_delete:"))
    async def delete_category(call: CallbackQuery, session_maker: async_sessionmaker) -> None:
        category_id = int(call.data.rsplit(":", 1)[-1])
        async with session_maker() as session:
            deleted = await CategoryRepository(session).delete(category_id)

        await call.answer("Категория удалена." if deleted else "Категория не найдена.", show_alert=not deleted)
        if not deleted:
            return

        await log_admin_action(
            session_maker,
            admin_id=call.from_user.id,
            action="category_delete",
            entity_type="category",
            entity_id=category_id,
        )
        await call.message.answer("Категория удалена. Товары сохранены и отвязаны от категории.")
        await show_categories(call.message, session_maker)
    @router.callback_query(F.data == "admin:add_product")
    async def add_product_start(call: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await state.set_state(CreateProductStates.title)
        await call.answer()
        await call.message.answer("Введите название товара.", reply_markup=simple_reply_keyboard(CANCEL_BUTTON))

    @router.message(CreateProductStates.title, F.text)
    async def add_product_title(message: Message, state: FSMContext) -> None:
        try:
            title = validate_required_text(message.text, "Название товара", 255)
        except ValidationError as exc:
            await message.answer(str(exc))
            return

        await state.update_data(title=title)
        await state.set_state(CreateProductStates.short_description)
        await message.answer("Введите краткое описание товара.")

    @router.message(CreateProductStates.short_description, F.text)
    async def add_product_short_description(message: Message, state: FSMContext) -> None:
        try:
            value = validate_optional_text(message.text, "Краткое описание", 500)
        except ValidationError as exc:
            await message.answer(str(exc))
            return

        await state.update_data(short_description=value)
        await state.set_state(CreateProductStates.full_description)
        await message.answer("Введите полное описание товара.")

    @router.message(CreateProductStates.full_description, F.text)
    async def add_product_full_description(message: Message, state: FSMContext) -> None:
        try:
            value = validate_optional_text(message.text, "Полное описание", 3000)
        except ValidationError as exc:
            await message.answer(str(exc))
            return

        await state.update_data(full_description=value)
        await state.set_state(CreateProductStates.delivery_content)
        await message.answer("Введите текст, который нужно отправить вместе с ZIP, или нажмите «Пропустить».", reply_markup=skip_cancel_keyboard())

    @router.message(CreateProductStates.delivery_content, F.text)
    async def add_product_delivery_content(message: Message, state: FSMContext) -> None:
        try:
            value = None if message.text == SKIP_BUTTON else validate_optional_text(message.text, "Текст после выдачи", 12000)
        except ValidationError as exc:
            await message.answer(str(exc))
            return

        await state.update_data(delivery_content=value)
        await state.set_state(CreateProductStates.price)
        await message.answer("Введите цену, например 19.99", reply_markup=simple_reply_keyboard(CANCEL_BUTTON))

    @router.message(CreateProductStates.price, F.text)
    async def add_product_price(message: Message, state: FSMContext) -> None:
        try:
            price = validate_price(message.text)
        except ValidationError as exc:
            await message.answer(str(exc))
            return

        await state.update_data(price=price)
        await state.set_state(CreateProductStates.sku)
        await message.answer("Введите SKU товара.")

    @router.message(CreateProductStates.sku, F.text)
    async def add_product_sku(message: Message, state: FSMContext, session_maker: async_sessionmaker) -> None:
        try:
            sku = validate_sku(message.text)
        except ValidationError as exc:
            await message.answer(str(exc))
            return

        async with session_maker() as session:
            product = await ProductRepository(session).get_by_sku(sku)

        if product:
            await message.answer("SKU уже существует. Введите другой.")
            return

        await state.update_data(sku=sku)
        await state.set_state(CreateProductStates.image)
        await message.answer(
            "Отправьте фото товара, file_id/URL картинки или нажмите «Пропустить».",
            reply_markup=skip_cancel_keyboard(),
        )

    async def ask_new_product_category(message: Message, session_maker: async_sessionmaker) -> None:
        async with session_maker() as session:
            categories = await CategoryRepository(session).list_all()

        await message.answer(
            "Выберите категорию товара.",
            reply_markup=category_picker_keyboard(categories, prefix="admin:new_product:category", include_empty=True),
        )

    @router.message(CreateProductStates.image, F.photo)
    async def add_product_image_photo(message: Message, state: FSMContext, session_maker: async_sessionmaker) -> None:
        await state.update_data(image=message.photo[-1].file_id)
        await state.set_state(CreateProductStates.category)
        await ask_new_product_category(message, session_maker)

    @router.message(CreateProductStates.image, F.text)
    async def add_product_image_text(message: Message, state: FSMContext, session_maker: async_sessionmaker) -> None:
        image = None if message.text == SKIP_BUTTON else message.text.strip()
        if image and len(image) > 255:
            await message.answer("Ссылка или file_id для фото слишком длинные. Максимум 255 символов.")
            return
        await state.update_data(image=image)
        await state.set_state(CreateProductStates.category)
        await ask_new_product_category(message, session_maker)

    @router.callback_query(CreateProductStates.category, F.data.startswith("admin:new_product:category:"))
    async def add_product_category(call: CallbackQuery, state: FSMContext) -> None:
        raw_value = call.data.rsplit(":", 1)[-1]
        category_id = None if raw_value == "none" else int(raw_value)
        await state.update_data(category_id=category_id)
        await state.set_state(CreateProductStates.stock_status)
        await call.answer()
        await call.message.answer("Выберите статус наличия.", reply_markup=stock_status_keyboard("admin:new_product:stock"))

    @router.callback_query(CreateProductStates.stock_status, F.data.startswith("admin:new_product:stock:"))
    async def add_product_stock(call: CallbackQuery, state: FSMContext) -> None:
        stock_status = call.data.rsplit(":", 1)[-1]
        await state.update_data(stock_status=stock_status)
        await state.set_state(CreateProductStates.is_active)
        await call.answer()
        await call.message.answer("Сделать товар активным сразу?", reply_markup=yes_no_keyboard("admin:new_product:active"))

    @router.callback_query(CreateProductStates.is_active, F.data.startswith("admin:new_product:active:"))
    async def add_product_finish(call: CallbackQuery, state: FSMContext, session_maker: async_sessionmaker, config: Config) -> None:
        is_active = call.data.rsplit(":", 1)[-1] == "yes"
        data = await state.get_data()

        async with session_maker() as session:
            product = await ProductRepository(session).create(
                title=data["title"],
                short_description=data.get("short_description"),
                full_description=data.get("full_description"),
                delivery_content=data.get("delivery_content"),
                price=data["price"],
                image=data.get("image"),
                category_id=data.get("category_id"),
                sku=data["sku"],
                stock_status=data["stock_status"],
                is_active=is_active,
            )

        await state.clear()
        await call.answer("Товар создан.")

        if not product:
            await call.message.answer("Не удалось создать товар. Проверьте SKU и попробуйте снова.")
            return

        await log_admin_action(
            session_maker,
            admin_id=call.from_user.id,
            action="product_create",
            entity_type="product",
            entity_id=product.id,
            payload={
                "title": product.title,
                "sku": product.sku,
                "category_id": product.category_id,
                "stock_status": product.stock_status,
                "is_active": product.is_active,
                "has_delivery_content": bool(product.delivery_content),
            },
        )

        await call.message.answer(
            f"Товар <b>{escape(product.title)}</b> создан.",
            reply_markup=main_menu_keyboard(is_admin=call.from_user.id == config.admin_id),
        )
        await call.message.answer(admin_product_caption(product, config.currency), reply_markup=admin_product_actions_keyboard(product.id, product.is_active))

    @router.callback_query(F.data.startswith("admin:product:"))
    async def open_admin_product(call: CallbackQuery, session_maker: async_sessionmaker, config: Config) -> None:
        product_id = int(call.data.rsplit(":", 1)[-1])
        async with session_maker() as session:
            product = await ProductRepository(session).get(product_id)

        await call.answer()
        if not product:
            await call.message.answer("Товар не найден.")
            return

        await call.message.answer(admin_product_caption(product, config.currency), reply_markup=admin_product_actions_keyboard(product.id, product.is_active))

    @router.callback_query(F.data.startswith("admin:toggle_active:"))
    async def toggle_product_active(call: CallbackQuery, session_maker: async_sessionmaker, config: Config) -> None:
        product_id = int(call.data.rsplit(":", 1)[-1])
        async with session_maker() as session:
            repo = ProductRepository(session)
            product = await repo.get(product_id)
            if not product:
                await call.answer("Товар не найден.", show_alert=True)
                return
            product = await repo.update(product_id, is_active=not product.is_active)

        await call.answer("Статус товара изменен.")
        if not product:
            await call.message.answer("Не удалось обновить товар.")
            return

        await log_admin_action(
            session_maker,
            admin_id=call.from_user.id,
            action="product_toggle_active",
            entity_type="product",
            entity_id=product.id,
            payload={"is_active": product.is_active},
        )
        await call.message.answer(admin_product_caption(product, config.currency), reply_markup=admin_product_actions_keyboard(product.id, product.is_active))

    @router.callback_query(F.data.startswith("admin:delete:"))
    async def delete_product_ask(call: CallbackQuery) -> None:
        product_id = int(call.data.rsplit(":", 1)[-1])
        await call.answer()
        await call.message.answer("Удалить товар без возможности восстановления?", reply_markup=confirm_delete_keyboard(product_id))

    @router.callback_query(F.data.startswith("admin:delete_confirm:"))
    async def delete_product_confirm(call: CallbackQuery, session_maker: async_sessionmaker) -> None:
        product_id = int(call.data.rsplit(":", 1)[-1])
        async with session_maker() as session:
            deleted = await ProductRepository(session).delete(product_id)

        if deleted:
            await log_admin_action(
                session_maker,
                admin_id=call.from_user.id,
                action="product_delete",
                entity_type="product",
                entity_id=product_id,
            )
            await call.answer("Товар удален.")
            await call.message.answer("Товар удален.")
        else:
            await call.answer("Товар не найден.", show_alert=True)

    @router.callback_query(F.data.startswith("admin:edit_menu:"))
    async def edit_menu(call: CallbackQuery) -> None:
        product_id = int(call.data.rsplit(":", 1)[-1])
        await call.answer()
        await call.message.answer("Что изменить в товаре?", reply_markup=admin_edit_fields_keyboard(product_id))

    @router.callback_query(F.data.startswith("admin:edit_field:"))
    async def edit_field_start(call: CallbackQuery, state: FSMContext, session_maker: async_sessionmaker) -> None:
        _, _, product_id_raw, field = call.data.split(":")
        product_id = int(product_id_raw)

        if field in {"category", "stock_status"}:
            if field == "category":
                async with session_maker() as session:
                    categories = await CategoryRepository(session).list_all()
                await call.answer()
                await call.message.answer(
                    "Выберите новую категорию.",
                    reply_markup=category_picker_keyboard(categories, prefix=f"admin:edit_category:{product_id}", include_empty=True),
                )
                return

            await call.answer()
            await call.message.answer("Выберите новый статус наличия.", reply_markup=stock_status_keyboard(f"admin:edit_stock:{product_id}"))
            return

        if field == "image":
            await state.set_state(EditProductStates.image)
            await state.update_data(product_id=product_id)
            await call.answer()
            await call.message.answer(
                "Отправьте новое фото, file_id/URL или нажмите «Удалить фото».",
                reply_markup=simple_reply_keyboard(REMOVE_PHOTO_BUTTON, CANCEL_BUTTON),
            )
            return

        if field == "delivery_files":
            await state.set_state(EditProductStates.delivery_files)
            await state.update_data(product_id=product_id)
            await call.answer()
            await call.message.answer(
                "Отправляйте ZIP-файлы по одному сообщению. Для синхронизации вариантов используйте одинаковый префикс до __, например acc001__tdata.zip и acc001__session.zip. Для товаров под заказ можно загружать ZIP-заглушки только для учета остатков.",
                reply_markup=simple_reply_keyboard(CANCEL_BUTTON),
            )
            return

        await state.set_state(EditProductStates.value)
        await state.update_data(product_id=product_id, field=field)
        await call.answer()
        await call.message.answer(f"Введите {TEXT_PRODUCT_FIELDS[field]} товара.", reply_markup=simple_reply_keyboard(CANCEL_BUTTON))

    @router.message(EditProductStates.value, F.text)
    async def edit_field_value(message: Message, state: FSMContext, session_maker: async_sessionmaker, config: Config) -> None:
        data = await state.get_data()
        product_id = data["product_id"]
        field = data["field"]
        raw_value = message.text.strip()

        try:
            if field == "title":
                value = validate_required_text(raw_value, "Название товара", 255)
            elif field == "short_description":
                value = validate_optional_text(raw_value, "Краткое описание", 500)
            elif field == "full_description":
                value = validate_optional_text(raw_value, "Полное описание", 3000)
            elif field == "delivery_content":
                value = validate_optional_text(raw_value, "Текст после выдачи", 12000)
            elif field == "price":
                value = validate_price(raw_value)
            elif field == "sku":
                value = validate_sku(raw_value)
            else:
                value = raw_value
        except ValidationError as exc:
            await message.answer(str(exc))
            return

        if field == "sku":
            async with session_maker() as session:
                product = await ProductRepository(session).get_by_sku(value)
            if product and product.id != product_id:
                await message.answer("Такой SKU уже используется. Введите другой.")
                return

        async with session_maker() as session:
            product = await ProductRepository(session).update(product_id, **{field: value})

        await state.clear()
        if not product:
            await message.answer("Не удалось обновить товар.")
            return

        await log_admin_action(
            session_maker,
            admin_id=message.from_user.id,
            action="product_update",
            entity_type="product",
            entity_id=product.id,
            payload={field: str(value)},
        )
        await message.answer("Товар обновлен.", reply_markup=main_menu_keyboard(is_admin=message.from_user.id == config.admin_id))
        await message.answer(admin_product_caption(product, config.currency), reply_markup=admin_product_actions_keyboard(product.id, product.is_active))

    @router.message(EditProductStates.image, F.photo)
    async def edit_product_image_photo(message: Message, state: FSMContext, session_maker: async_sessionmaker, config: Config) -> None:
        data = await state.get_data()
        async with session_maker() as session:
            product = await ProductRepository(session).update(data["product_id"], image=message.photo[-1].file_id)

        await state.clear()
        if not product:
            await message.answer("Не удалось обновить товар.")
            return

        await log_admin_action(
            session_maker,
            admin_id=message.from_user.id,
            action="product_update_image",
            entity_type="product",
            entity_id=product.id,
            payload={"image": "telegram_file_id"},
        )
        await message.answer("Фото обновлено.", reply_markup=main_menu_keyboard(is_admin=message.from_user.id == config.admin_id))
        await message.answer(admin_product_caption(product, config.currency), reply_markup=admin_product_actions_keyboard(product.id, product.is_active))

    @router.message(EditProductStates.image, F.text)
    async def edit_product_image_text(message: Message, state: FSMContext, session_maker: async_sessionmaker, config: Config) -> None:
        data = await state.get_data()
        new_image = None if message.text == REMOVE_PHOTO_BUTTON else message.text.strip()
        if new_image and len(new_image) > 255:
            await message.answer("Ссылка или file_id для фото слишком длинные. Максимум 255 символов.")
            return

        async with session_maker() as session:
            product = await ProductRepository(session).update(data["product_id"], image=new_image)

        await state.clear()
        if not product:
            await message.answer("Не удалось обновить товар.")
            return

        await log_admin_action(
            session_maker,
            admin_id=message.from_user.id,
            action="product_update_image",
            entity_type="product",
            entity_id=product.id,
            payload={"image": new_image or None},
        )
        await message.answer("Фото обновлено.", reply_markup=main_menu_keyboard(is_admin=message.from_user.id == config.admin_id))
        await message.answer(admin_product_caption(product, config.currency), reply_markup=admin_product_actions_keyboard(product.id, product.is_active))

    @router.message(EditProductStates.delivery_files, F.document)
    async def upload_product_delivery_file(message: Message, state: FSMContext, session_maker: async_sessionmaker, config: Config) -> None:
        data = await state.get_data()
        document = message.document
        file_name = (document.file_name or "").strip()
        if not file_name.lower().endswith(".zip"):
            await message.answer("Нужен ZIP-файл. Отправьте архив с расширением .zip.")
            return

        async with session_maker() as session:
            delivery_repo = DeliveryFileRepository(session)
            product_repo = ProductRepository(session)
            delivery_file = await delivery_repo.add_file(
                product_id=data["product_id"],
                telegram_file_id=document.file_id,
                file_name=file_name,
            )
            product = await product_repo.get(data["product_id"])
            available_count = await delivery_repo.count_available(data["product_id"])

        await log_admin_action(
            session_maker,
            admin_id=message.from_user.id,
            action="product_upload_delivery_zip",
            entity_type="product",
            entity_id=data["product_id"],
            payload={"file_name": file_name},
        )
        sync_note = (
            f" Синхроключ: <code>{escape(delivery_file.sync_key)}</code>."
            if delivery_file.sync_key
            else " Для синхронизации вариантов используйте имя вида <code>acc001__tdata.zip</code>."
        )
        await message.answer(
            f"ZIP <b>{escape(file_name)}</b> добавлен в пул. Сейчас свободно: <b>{available_count}</b>.{sync_note}",
            reply_markup=simple_reply_keyboard(CANCEL_BUTTON),
        )
        if product:
            await message.answer(
                admin_product_caption(product, config.currency),
                reply_markup=admin_product_actions_keyboard(product.id, product.is_active),
            )

    @router.message(EditProductStates.delivery_files)
    async def upload_product_delivery_file_invalid(message: Message) -> None:
        await message.answer("Отправьте ZIP-файл документом или нажмите «Отмена».")

    @router.callback_query(F.data.startswith("admin:edit_category:"))
    async def edit_product_category(call: CallbackQuery, session_maker: async_sessionmaker, config: Config) -> None:
        _, _, product_id_raw, raw_value = call.data.split(":")
        product_id = int(product_id_raw)
        category_id = None if raw_value == "none" else int(raw_value)

        async with session_maker() as session:
            product = await ProductRepository(session).update(product_id, category_id=category_id)

        await call.answer("Категория обновлена.")
        if not product:
            await call.message.answer("Не удалось обновить товар.")
            return

        await log_admin_action(
            session_maker,
            admin_id=call.from_user.id,
            action="product_update_category",
            entity_type="product",
            entity_id=product.id,
            payload={"category_id": category_id},
        )
        await call.message.answer(admin_product_caption(product, config.currency), reply_markup=admin_product_actions_keyboard(product.id, product.is_active))

    @router.callback_query(F.data.startswith("admin:edit_stock:"))
    async def edit_product_stock(call: CallbackQuery, session_maker: async_sessionmaker, config: Config) -> None:
        _, _, product_id_raw, stock_status = call.data.split(":")
        product_id = int(product_id_raw)

        async with session_maker() as session:
            product = await ProductRepository(session).update(product_id, stock_status=stock_status)

        await call.answer("Наличие обновлено.")
        if not product:
            await call.message.answer("Не удалось обновить товар.")
            return

        await log_admin_action(
            session_maker,
            admin_id=call.from_user.id,
            action="product_update_stock",
            entity_type="product",
            entity_id=product.id,
            payload={"stock_status": stock_status},
        )
        await call.message.answer(admin_product_caption(product, config.currency), reply_markup=admin_product_actions_keyboard(product.id, product.is_active))

    @router.callback_query(F.data.startswith("admin:order:"))
    async def open_order(call: CallbackQuery, session_maker: async_sessionmaker, config: Config) -> None:
        order_id = int(call.data.rsplit(":", 1)[-1])
        async with session_maker() as session:
            order = await OrderRepository(session).get(order_id)

        await call.answer()
        if not order:
            await call.message.answer("Заказ не найден.")
            return

        await call.message.answer(order_text(order, config.currency, include_customer=True), reply_markup=admin_order_keyboard(order.id))

    @router.callback_query(F.data.startswith("admin:order_deliver:"))
    async def manual_deliver_order(call: CallbackQuery, state: FSMContext, session_maker: async_sessionmaker, config: Config, bot: Bot) -> None:
        order_id = int(call.data.rsplit(":", 1)[-1])
        async with session_maker() as session:
            order = await OrderRepository(session).get(order_id)

        if not order:
            await call.answer("Заказ не найден.", show_alert=True)
            return

        has_preorder_items = any(item.stock_status == "preorder" for item in order.items)
        if has_preorder_items:
            if order.preorder_delivery_sent_at:
                await call.answer("Выдача уже выполнена.", show_alert=True)
                return

            await state.clear()
            await state.set_state(ManualOrderDeliveryStates.document)
            await state.update_data(order_id=order.id)
            await call.answer()
            await call.message.answer("Отправьте файл документом, и я выдам его покупателю по этому заказу.", reply_markup=simple_reply_keyboard(CANCEL_BUTTON))
            return

        try:
            delivered = await deliver_order_digital_content(
                bot=bot,
                session_maker=session_maker,
                order_id=order.id,
                admin_id=config.admin_id,
                include_preorder=True,
            )
        except Exception:
            delivered = False

        await log_admin_action(
            session_maker,
            admin_id=call.from_user.id,
            action="order_manual_delivery",
            entity_type="order",
            entity_id=order.id,
            payload={"delivered": delivered},
        )

        if delivered:
            await call.answer("Выдача отправлена.")
            await call.message.answer("Товар отправлен покупателю вручную из админки.")
        else:
            await call.answer("Выдача не выполнена.", show_alert=True)
            await call.message.answer("Не удалось выполнить выдачу. Проверьте ZIP-пул, статус заказа и наличие уже отправленной выдачи.")
    @router.message(ManualOrderDeliveryStates.document, F.document)
    async def send_manual_order_document(message: Message, state: FSMContext, session_maker: async_sessionmaker, config: Config, bot: Bot) -> None:
        data = await state.get_data()
        order_id = data.get("order_id")
        if not order_id:
            await state.clear()
            await message.answer("Не удалось определить заказ для выдачи.")
            return

        async with session_maker() as session:
            order = await OrderRepository(session).get(order_id)

        if not order:
            await state.clear()
            await message.answer("Заказ не найден.")
            return

        document = message.document
        caption = f"Заказ #{order.id}"
        if document.file_name:
            caption += f"\n{escape(document.file_name)}"

        try:
            await bot.send_document(order.user_id, document.file_id, caption=caption)
            async with session_maker() as session:
                updated_order = await OrderRepository(session).mark_preorder_delivery_sent(order.id)
        except Exception:
            await message.answer("Не удалось отправить файл покупателю.")
            return

        await log_admin_action(
            session_maker,
            admin_id=message.from_user.id,
            action="order_manual_delivery_upload",
            entity_type="order",
            entity_id=order.id,
            payload={"file_name": document.file_name or None},
        )

        await state.clear()
        await message.answer("Файл отправлен покупателю.", reply_markup=main_menu_keyboard(is_admin=message.from_user.id == config.admin_id))
        if updated_order:
            await message.answer(order_text(updated_order, config.currency, include_customer=True), reply_markup=admin_order_keyboard(updated_order.id))

    @router.message(ManualOrderDeliveryStates.document)
    async def send_manual_order_document_invalid(message: Message) -> None:
        await message.answer("Отправьте файл документом или нажмите «Отмена».")
    @router.callback_query(F.data.startswith("admin:order_status:"))
    async def update_order_status(call: CallbackQuery, session_maker: async_sessionmaker, config: Config, bot: Bot) -> None:
        _, _, order_id_raw, status = call.data.split(":")
        order_id = int(order_id_raw)

        async with session_maker() as session:
            order = await OrderRepository(session).update_status(order_id, status)

        if not order:
            await call.answer("Заказ не найден.", show_alert=True)
            return

        await log_admin_action(
            session_maker,
            admin_id=call.from_user.id,
            action="order_update_status",
            entity_type="order",
            entity_id=order.id,
            payload={"status": status},
        )
        await call.answer("Статус заказа обновлен.")
        await call.message.answer(order_text(order, config.currency, include_customer=True), reply_markup=admin_order_keyboard(order.id))

        status_label = ORDER_STATUS_LABELS.get(status, status)
        try:
            await bot.send_message(order.user_id, f"Статус вашего заказа <b>#{order.id}</b> изменен: <b>{escape(status_label)}</b>.")
        except Exception:
            pass

        if status in {"paid", "completed"}:
            try:
                await deliver_order_digital_content(bot=bot, session_maker=session_maker, order_id=order.id, admin_id=config.admin_id, include_preorder=False)
            except Exception:
                pass

    return router






















