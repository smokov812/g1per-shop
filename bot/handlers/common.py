from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message, MessageEntity

from bot.const import (
    CANCEL_BUTTON,
    MAIN_MENU_BUTTON,
    SERVICE_BACK_BUTTON,
    SERVICE_BUTTON,
    SERVICE_CHANNEL_BUTTON,
    SERVICE_OFFER_BUTTON,
    SERVICE_PRIVACY_BUTTON,
    SERVICE_SUPPORT_BUTTON,
    SERVICE_TERMS_BUTTON,
    button_matches,
)
from bot.keyboards.user import main_menu_keyboard, service_menu_keyboard

BANNER_PATH = Path(__file__).resolve().parents[2] / "banner.png"
CUSTOM_EMOJI_ID = "7173162320003080"
CUSTOM_EMOJI_FALLBACK = "✨"
logger = logging.getLogger(__name__)
_cached_custom_emoji_alt: str | None = None


def _utf16_len(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


async def _resolve_custom_emoji_alt(message: Message) -> str:
    global _cached_custom_emoji_alt
    if _cached_custom_emoji_alt:
        return _cached_custom_emoji_alt

    alt = CUSTOM_EMOJI_FALLBACK
    try:
        stickers = await message.bot.get_custom_emoji_stickers([CUSTOM_EMOJI_ID])
        if stickers:
            sticker_emoji = getattr(stickers[0], "emoji", None)
            if isinstance(sticker_emoji, str) and sticker_emoji:
                alt = sticker_emoji
    except Exception as exc:
        logger.warning("Failed to resolve custom emoji %s: %s", CUSTOM_EMOJI_ID, exc)

    _cached_custom_emoji_alt = alt
    return alt


async def _answer_with_custom_emoji(
    message: Message,
    body: str,
    *,
    reply_markup=None,
) -> None:
    alt = await _resolve_custom_emoji_alt(message)
    text = f"{alt} {body}"
    entities = [
        MessageEntity(
            type="custom_emoji",
            offset=0,
            length=_utf16_len(alt),
            custom_emoji_id=CUSTOM_EMOJI_ID,
        )
    ]

    try:
        await message.answer(text, entities=entities, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        logger.warning("Failed to send custom emoji text: %s", exc)
        await message.answer(text, reply_markup=reply_markup)


def get_common_router(
    admin_id: int,
    support_username: str = "",
    *,
    offer_url: str = "",
    privacy_url: str = "",
    terms_url: str = "",
    channel_url: str = "",
) -> Router:
    router = Router(name="common")
    has_service = any(
        value.strip()
        for value in (support_username, offer_url, privacy_url, terms_url, channel_url)
    )

    def normalize_username(value: str) -> str:
        username = value.strip()
        if username and not username.startswith("@"):
            username = f"@{username}"
        return username

    def support_text() -> str:
        username = normalize_username(support_username)
        if not username:
            return "Тех. поддержка\n\nКонтакт поддержки пока не указан."
        return (
            "Тех. поддержка\n\n"
            f"Контакт: {username}\n"
            f"Ссылка:\nhttps://t.me/{username.lstrip('@')}"
        )

    def link_text(title: str, url: str) -> str:
        link = url.strip()
        if not link:
            return f"{title}\n\nБудет добавлено позже."
        return (
            f"{title}\n\n"
            "Открыть документ:\n"
            f"{link}"
        )

    @router.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        is_admin = message.from_user.id == admin_id
        username = (
            f"@{message.from_user.username}"
            if message.from_user.username
            else message.from_user.first_name or "друг"
        )
        text = (
            f"👋 Добро пожаловать, <b>{username}</b>\n\n"
            "G1PER SHOP — цифровой магазин в Telegram.\n"
            "Выберите нужный раздел в меню ниже."
        )

        keyboard = main_menu_keyboard(is_admin=is_admin, has_service=has_service)
        if BANNER_PATH.exists():
            try:
                await message.answer_photo(FSInputFile(BANNER_PATH), caption=text, reply_markup=keyboard)
                return
            except TelegramBadRequest as exc:
                logger.warning("Failed to send banner %s: %s", BANNER_PATH, exc)

        await message.answer(text, reply_markup=keyboard)

    @router.message(Command("cancel"))
    @router.message(lambda message: button_matches(message.text, CANCEL_BUTTON))
    async def cancel_action(message: Message, state: FSMContext) -> None:
        current_state = await state.get_state()
        keyboard = main_menu_keyboard(
            is_admin=message.from_user.id == admin_id, has_service=has_service
        )
        if current_state:
            await state.clear()
            await message.answer("Текущее действие отменено.", reply_markup=keyboard)
        else:
            await message.answer("Сейчас нет активного сценария.", reply_markup=keyboard)

    @router.message(lambda message: button_matches(message.text, MAIN_MENU_BUTTON))
    async def show_main_menu(message: Message) -> None:
        await _answer_with_custom_emoji(
            message,
            "Главное меню\n\nВыберите нужный раздел ниже.",
            reply_markup=main_menu_keyboard(
                is_admin=message.from_user.id == admin_id,
                has_service=has_service,
            ),
        )

    @router.message(lambda message: button_matches(message.text, SERVICE_BUTTON))
    async def show_service_menu(message: Message) -> None:
        await _answer_with_custom_emoji(
            message,
            "О сервисе\n\nВыберите нужный раздел ниже.",
            reply_markup=service_menu_keyboard(),
        )

    @router.message(lambda message: button_matches(message.text, SERVICE_OFFER_BUTTON))
    async def show_offer(message: Message) -> None:
        await _answer_with_custom_emoji(
            message,
            link_text("Оферта", offer_url),
            reply_markup=service_menu_keyboard(),
        )

    @router.message(lambda message: button_matches(message.text, SERVICE_PRIVACY_BUTTON))
    async def show_privacy(message: Message) -> None:
        await _answer_with_custom_emoji(
            message,
            link_text("Политика конфиденциальности", privacy_url),
            reply_markup=service_menu_keyboard(),
        )

    @router.message(lambda message: button_matches(message.text, SERVICE_TERMS_BUTTON))
    async def show_terms(message: Message) -> None:
        await _answer_with_custom_emoji(
            message,
            link_text("Пользовательское соглашение", terms_url),
            reply_markup=service_menu_keyboard(),
        )

    @router.message(lambda message: button_matches(message.text, SERVICE_CHANNEL_BUTTON))
    async def show_channel(message: Message) -> None:
        await _answer_with_custom_emoji(
            message,
            link_text("Новостной канал", channel_url),
            reply_markup=service_menu_keyboard(),
        )

    @router.message(lambda message: button_matches(message.text, SERVICE_SUPPORT_BUTTON))
    async def show_support(message: Message) -> None:
        await _answer_with_custom_emoji(
            message,
            support_text(),
            reply_markup=service_menu_keyboard(),
        )

    @router.message(lambda message: button_matches(message.text, SERVICE_BACK_BUTTON))
    async def service_back(message: Message) -> None:
        await _answer_with_custom_emoji(
            message,
            "Главное меню\n\nВыберите нужный раздел ниже.",
            reply_markup=main_menu_keyboard(
                is_admin=message.from_user.id == admin_id,
                has_service=has_service,
            ),
        )

    return router
