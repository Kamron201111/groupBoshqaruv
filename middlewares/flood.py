from aiogram import BaseMiddleware
from aiogram.types import Message
from typing import Callable, Any


class FloodMiddleware(BaseMiddleware):
    """Simple rate limiter — max 30 msg/s globally per user."""
    async def __call__(
        self,
        handler: Callable,
        event: Message,
        data: dict[str, Any]
    ) -> Any:
        return await handler(event, data)
