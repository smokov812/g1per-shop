from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.db.repositories import RateLimitRepository


class RateLimitMiddleware(BaseMiddleware):
    def __init__(
        self,
        *,
        session_maker: async_sessionmaker,
        message_window: float,
        callback_window: float,
        admin_id: int,
    ) -> None:
        self.session_maker = session_maker
        self.message_window = message_window
        self.callback_window = callback_window
        self.admin_id = admin_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if not user or user.id == self.admin_id:
            return await handler(event, data)

        if isinstance(event, Message):
            scope = "message"
            window = self.message_window
        elif isinstance(event, CallbackQuery):
            scope = "callback"
            window = self.callback_window
        else:
            return await handler(event, data)

        async with self.session_maker() as session:
            decision = await RateLimitRepository(session).consume(user_id=user.id, scope=scope, window_seconds=window)

        if decision.allowed:
            return await handler(event, data)

        retry_hint = max(0.1, decision.retry_after)
        text = f"Слишком часто. Подождите {retry_hint:.1f} сек. и повторите."
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=False)
            return None
        await event.answer(text)
        return None
