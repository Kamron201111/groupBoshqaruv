import re
from aiogram import Router, Bot, F
from aiogram.types import Message
from database import get_group
from utils import is_admin

router = Router()

LINK_PATTERN = re.compile(
    r"(https?://|t\.me/|@\w{5,}|www\.|bit\.ly|tinyurl\.com)",
    re.IGNORECASE
)


@router.message(F.text)
async def antilink_check(message: Message, bot: Bot):
    if message.chat.type == "private":
        return
    if not message.text:
        return
    if await is_admin(bot, message.chat.id, message.from_user.id):
        return

    group = await get_group(message.chat.id)
    if not group or not group.get("anti_link"):
        return

    if LINK_PATTERN.search(message.text):
        try:
            await message.delete()
            warn_msg = await message.answer(
                f"🔗❌ {message.from_user.mention_html()} — havolalar taqiqlangan!"
            )
            import asyncio
            await asyncio.sleep(5)
            await warn_msg.delete()
        except Exception:
            pass
