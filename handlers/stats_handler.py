from aiogram import Router, Bot
from aiogram.types import Message
from aiogram.filters import Command
from database import get_top_members, get_group_stats
from utils import mention_html

router = Router()

MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


@router.message(Command("stats"))
async def cmd_stats(message: Message, bot: Bot):
    if message.chat.type == "private":
        return
    s = await get_group_stats(message.chat.id)
    count = await bot.get_chat_member_count(message.chat.id)
    text = (
        f"📊 <b>Guruh statistikasi — {message.chat.title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Jami a'zolar: <b>{count}</b>\n"
        f"💬 Jami xabarlar: <b>{s['messages']}</b>\n"
        f"🔨 Banlar: <b>{s['bans']}</b>\n"
        f"⚠️ Ogohlantirish: <b>{s['warns']}</b>\n"
        f"🔇 Mutlar: <b>{s['mutes']}</b>\n"
    )
    await message.reply(text)


@router.message(Command("top"))
async def cmd_top(message: Message, bot: Bot):
    if message.chat.type == "private":
        return
    top = await get_top_members(message.chat.id, limit=10)
    if not top:
        return await message.reply("📊 Hali ma'lumot yo'q.")
    text = f"🏆 <b>TOP 10 — {message.chat.title}</b>\n\n"
    for i, m in enumerate(top):
        medal = MEDALS[i] if i < len(MEDALS) else f"{i+1}."
        name = m["full_name"] or m["username"] or f"User {m['user_id']}"
        text += f"{medal} {mention_html(m['user_id'], name)} — {m['message_count']} xabar\n"
    await message.reply(text)
