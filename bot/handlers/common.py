from __future__ import annotations

from pathlib import Path

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

from bot.const import CANCEL_BUTTON, MAIN_MENU_BUTTON, SUPPORT_BUTTON, button_matches
from bot.keyboards.user import main_menu_keyboard

BANNER_PATH = Path(__file__).resolve().parents[2] / "banner.png"


def get_common_router(admin_id: int, support_username: str = "") -> Router:
    router = Router(name="common")
    has_support = bool(support_username.strip())

    def build_support_text() -> str:
        username = support_username.strip()
        if not username:
            return "Контакт поддержки пока не указан."
        if not username.startswith("@"):
            username = f"@{username}"
        return f"Поддержка: {username}\nПрямая ссылка: https://t.me/{username.lstrip('@')}"

    @router.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        is_admin = message.from_user.id == admin_id
        text = (
            "Привет. Это универсальный Telegram-магазин.\n\n"
            "Бот умеет показывать каталог, добавлять товары в корзину, "
            "оформлять заказы и принимать оплату через подключенные способы."
        )

        keyboard = main_menu_keyboard(is_admin=is_admin, has_support=has_support)
        if BANNER_PATH.exists():
            await message.answer_photo(FSInputFile(BANNER_PATH), caption=text, reply_markup=keyboard)
        else:
            await message.answer(text, reply_markup=keyboard)

    @router.message(Command("cancel"))
    @router.message(lambda message: button_matches(message.text, CANCEL_BUTTON))
    async def cancel_action(message: Message, state: FSMContext) -> None:
        current_state = await state.get_state()
        keyboard = main_menu_keyboard(is_admin=message.from_user.id == admin_id, has_support=has_support)
        if current_state:
            await state.clear()
            await message.answer("Текущее действие отменено.", reply_markup=keyboard)
        else:
            await message.answer("Сейчас нет активного сценария.", reply_markup=keyboard)

    @router.message(lambda message: button_matches(message.text, MAIN_MENU_BUTTON))
    async def show_main_menu(message: Message) -> None:
        await message.answer(
            "Главное меню.",
            reply_markup=main_menu_keyboard(
                is_admin=message.from_user.id == admin_id,
                has_support=has_support,
            ),
        )

    @router.message(lambda message: button_matches(message.text, SUPPORT_BUTTON))
    async def show_support(message: Message) -> None:
        await message.answer(build_support_text())

    return router
