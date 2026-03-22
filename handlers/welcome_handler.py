from aiogram import Router, Bot, F
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION, LEAVE_TRANSITION
from database import upsert_group, upsert_member, upsert_user, get_group
from utils import mention_html

router = Router()

DEFAULT_WELCOME = "👋 Xush kelibsiz, {mention}!\n🎉 Siz guruhning #{number} a'zosisiz."
DEFAULT_GOODBYE = "👋 {first_name} guruhni tark etdi."


def format_message(template: str, user, number: int = 0, chat_title: str = "") -> str:
    return (
        template
        .replace("{mention}", mention_html(user.id, user.full_name))
        .replace("{username}", f"@{user.username}" if user.username else user.full_name)
        .replace("{first_name}", user.first_name or "")
        .replace("{last_name}", user.last_name or "")
        .replace("{number}", str(number))
        .replace("{chat_title}", chat_title)
        .replace("{user_id}", str(user.id))
    )


@router.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def on_user_join(event: ChatMemberUpdated, bot: Bot):
    user = event.new_chat_member.user
    if user.is_bot:
        return

    chat = event.chat
    await upsert_group(chat.id, chat.title, chat.username)
    await upsert_user(user.id, user.username, user.full_name)
    await upsert_member(chat.id, user.id)

    group = await get_group(chat.id)
    if not group or not group.get("welcome_enabled", 1):
        return

    template = group.get("welcome_text") or DEFAULT_WELCOME
    count = await bot.get_chat_member_count(chat.id)
    text = format_message(template, user, number=count, chat_title=chat.title)
    await bot.send_message(chat.id, text)


@router.chat_member(ChatMemberUpdatedFilter(LEAVE_TRANSITION))
async def on_user_leave(event: ChatMemberUpdated, bot: Bot):
    user = event.old_chat_member.user
    if user.is_bot:
        return

    chat = event.chat
    group = await get_group(chat.id)
    if not group or not group.get("goodbye_enabled", 1):
        return

    template = DEFAULT_GOODBYE
    text = format_message(template, user, chat_title=chat.title)
    await bot.send_message(chat.id, text)
