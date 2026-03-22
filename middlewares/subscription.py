from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from typing import Callable, Any
from database import get_required_channels
from utils import is_admin


class SubscriptionMiddleware(BaseMiddleware):
    def __init__(self, bot: Bot):
        self.bot = bot
        super().__init__()

    async def __call__(
        self,
        handler: Callable,
        event: Message,
        data: dict[str, Any]
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)
        if event.chat.type == "private":
            return await handler(event, data)
        if not event.from_user or event.from_user.is_bot:
            return await handler(event, data)

        # Admins bypass subscription check
        if await is_admin(self.bot, event.chat.id, event.from_user.id):
            return await handler(event, data)

        channels = await get_required_channels(event.chat.id)
        if not channels:
            return await handler(event, data)

        not_subscribed = []
        for ch in channels:
            try:
                member = await self.bot.get_chat_member(ch["channel_id"], event.from_user.id)
                if member.status in ("left", "kicked", "banned"):
                    not_subscribed.append(ch)
            except Exception:
                not_subscribed.append(ch)

        if not_subscribed:
            buttons = []
            for ch in not_subscribed:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"📢 {ch['channel_title']}",
                        url=f"https://t.me/{ch['channel_username']}"
                    )
                ])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            try:
                await event.reply(
                    f"❗️ {event.from_user.mention_html()}, xabar yozish uchun quyidagi kanallarga obuna bo'ling:",
                    reply_markup=keyboard
                )
                await event.delete()
            except Exception:
                pass
            return  # Block the message

        return await handler(event, data)
