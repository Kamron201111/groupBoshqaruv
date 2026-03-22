from aiogram import Router, Bot, F
from aiogram.types import Message
from collections import defaultdict
from datetime import datetime, timedelta
from database import get_group, log_mute
from utils import MUTE_PERMISSIONS, is_admin
from config import FLOOD_LIMIT, FLOOD_TIME, FLOOD_MUTE_DURATION

router = Router()

# { (chat_id, user_id): [timestamps] }
flood_data: dict[tuple, list] = defaultdict(list)


@router.message()
async def antiflood_check(message: Message, bot: Bot):
    if message.chat.type == "private":
        return
    if not message.from_user:
        return
    if await is_admin(bot, message.chat.id, message.from_user.id):
        return

    group = await get_group(message.chat.id)
    if not group or not group.get("anti_flood", 1):
        return

    key = (message.chat.id, message.from_user.id)
    now = datetime.now()

    # Remove old timestamps
    flood_data[key] = [
        t for t in flood_data[key]
        if now - t < timedelta(seconds=FLOOD_TIME)
    ]
    flood_data[key].append(now)

    if len(flood_data[key]) >= FLOOD_LIMIT:
        flood_data[key] = []
        try:
            from datetime import timedelta as td
            until = now + td(seconds=FLOOD_MUTE_DURATION)
            await bot.restrict_chat_member(
                message.chat.id,
                message.from_user.id,
                MUTE_PERMISSIONS,
                until_date=until
            )
            await log_mute(
                message.chat.id, message.from_user.id, 0,
                f"{FLOOD_MUTE_DURATION}s", str(until), "Anti-flood"
            )
            warn = await message.answer(
                f"🌊 {message.from_user.mention_html()} — flood aniqlandi! "
                f"{FLOOD_MUTE_DURATION // 60} daqiqa jim qilindi."
            )
            import asyncio
            await asyncio.sleep(10)
            try:
                await warn.delete()
            except Exception:
                pass
        except Exception:
            pass
