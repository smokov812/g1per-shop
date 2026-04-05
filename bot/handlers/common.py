from __future__ import annotations

from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

from bot.const import CANCEL_BUTTON, MAIN_MENU_BUTTON, button_matches
from bot.keyboards.user import main_menu_keyboard

BANNER_PATH = Path(__file__).resolve().parents[2] / "banner.png"


def get_common_router(admin_id: int) -> Router:
    router = Router(name="common")

    @router.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        is_admin = message.from_user.id == admin_id
        text = (
            "Привет. Это универсальный Telegram-магазин.\n\n"
            "Бот умеет показывать каталог, добавлять товары в корзину, "
            "оформлять заказы и принимать оплату через подключенные способы."
        )
        if BANNER_PATH.exists():
            await message.answer_photo(FSInputFile(BANNER_PATH), caption=text, reply_markup=main_menu_keyboard(is_admin=is_admin))
        else:
            await message.answer(text, reply_markup=main_menu_keyboard(is_admin=is_admin))

    @router.message(Command("cancel"))
    @router.message(lambda message: button_matches(message.text, CANCEL_BUTTON))
    async def cancel_action(message: Message, state: FSMContext) -> None:
        current_state = await state.get_state()
        if current_state:
            await state.clear()
            await message.answer(
                "Текущее действие отменено.",
                reply_markup=main_menu_keyboard(is_admin=message.from_user.id == admin_id),
            )
        else:
            await message.answer(
                "Сейчас нет активного сценария.",
                reply_markup=main_menu_keyboard(is_admin=message.from_user.id == admin_id),
            )

    @router.message(lambda message: button_matches(message.text, MAIN_MENU_BUTTON))
    async def show_main_menu(message: Message) -> None:
        await message.answer(
            "Главное меню.",
            reply_markup=main_menu_keyboard(is_admin=message.from_user.id == admin_id),
        )

    return router

