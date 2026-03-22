from aiogram import Router, Bot, F
from aiogram.types import Message
from aiogram.filters import Command
from database import (
    increment_message_count, upsert_user, upsert_member,
    upsert_group, get_filters, get_blacklist, get_note
)
from utils import is_admin, MUTE_PERMISSIONS
import asyncio

router = Router()


@router.message()
async def handle_all_messages(message: Message, bot: Bot):
    if not message.from_user or message.from_user.is_bot:
        return
    if message.chat.type == "private":
        return

    user = message.from_user
    chat = message.chat

    # Upsert records
    await upsert_group(chat.id, chat.title, chat.username)
    await upsert_user(user.id, user.username, user.full_name)
    await upsert_member(chat.id, user.id)
    await increment_message_count(chat.id, user.id)

    text_lower = (message.text or "").lower().strip()

    # ── #note shortcut: #notename ─────────────────────────────
    if text_lower.startswith("#") and len(text_lower) > 1:
        note_name = text_lower[1:].split()[0]
        note = await get_note(chat.id, note_name)
        if note:
            await message.reply(note["content"])
            return

    # ── Blacklist check ───────────────────────────────────────
    if message.text and not await is_admin(bot, chat.id, user.id):
        blacklist = await get_blacklist(chat.id)
        for word in blacklist:
            if word in text_lower:
                try:
                    await message.delete()
                    warn = await message.answer(
                        f"🚫 {user.mention_html()} — taqiqlangan so'z ishlatdi!"
                    )
                    await asyncio.sleep(5)
                    await warn.delete()
                except Exception:
                    pass
                return

    # ── Filters (keyword auto-reply) ──────────────────────────
    if message.text:
        filters = await get_filters(chat.id)
        for f in filters:
            if f["keyword"] in text_lower:
                await message.reply(f["response"])
                return
