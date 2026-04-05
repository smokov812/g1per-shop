from bot.handlers.admin import get_admin_router
from bot.handlers.common import get_common_router
from bot.handlers.user import get_user_router

__all__ = ["get_common_router", "get_user_router", "get_admin_router"]
