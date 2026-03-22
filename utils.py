import re
from datetime import datetime, timedelta
from aiogram import Bot
from aiogram.types import Message, ChatPermissions
from aiogram.exceptions import TelegramBadRequest


# ─── TIME PARSER ─────────────────────────────────────────────────────────────
# Examples: 1m, 2h, 3d, 1w  →  timedelta

TIME_REGEX = re.compile(r"^(\d+)(s|m|h|d|w)$", re.IGNORECASE)
TIME_LABELS = {"s": "soniya", "m": "daqiqa", "h": "soat", "d": "kun", "w": "hafta"}
TIME_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(text: str) -> tuple[timedelta | None, str]:
    """Returns (timedelta, human_readable) or (None, '') if invalid."""
    m = TIME_REGEX.match(text.strip())
    if not m:
        return None, ""
    amount, unit = int(m.group(1)), m.group(2).lower()
    td = timedelta(seconds=amount * TIME_SECONDS[unit])
    human = f"{amount} {TIME_LABELS[unit]}"
    return td, human


def mute_until_str(duration: timedelta) -> str:
    return (datetime.now() + duration).strftime("%Y-%m-%d %H:%M:%S")


# ─── PERMISSION SHORTCUTS ─────────────────────────────────────────────────────

FULL_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_media_messages=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_change_info=False,
    can_invite_users=True,
    can_pin_messages=False,
)

MUTE_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_media_messages=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
)


# ─── ADMIN CHECK ─────────────────────────────────────────────────────────────

async def is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except TelegramBadRequest:
        return False


async def is_creator(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status == "creator"
    except TelegramBadRequest:
        return False


async def bot_is_admin(bot: Bot, chat_id: int) -> bool:
    me = await bot.get_me()
    return await is_admin(bot, chat_id, me.id)


# ─── MENTION ─────────────────────────────────────────────────────────────────

def mention_html(user_id: int, full_name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{full_name}</a>'


# ─── REPLY TARGET ─────────────────────────────────────────────────────────────
# Figures out target user from reply or user_id argument

async def resolve_target(message: Message, bot: Bot, args: list[str]):
    """
    Returns (user_id, full_name, reason) by:
      1. Checking replied message
      2. Checking first arg as @username or user_id
    """
    reason = ""
    if message.reply_to_message:
        user = message.reply_to_message.from_user
        reason = " ".join(args) if args else ""
        return user.id, user.full_name, reason

    if args:
        target_str = args[0]
        rest = args[1:]
        reason = " ".join(rest)
        try:
            uid = int(target_str)
            try:
                member = await bot.get_chat_member(message.chat.id, uid)
                return uid, member.user.full_name, reason
            except Exception:
                return uid, str(uid), reason
        except ValueError:
            username = target_str.lstrip("@")
            try:
                chat = await bot.get_chat(f"@{username}")
                return chat.id, chat.full_name or username, reason
            except Exception:
                pass

    return None, None, ""


# ─── FORMAT HELPERS ──────────────────────────────────────────────────────────

def escape_html(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def bold(text: str) -> str:
    return f"<b>{escape_html(str(text))}</b>"


def code(text: str) -> str:
    return f"<code>{escape_html(str(text))}</code>"
