from datetime import datetime
from aiogram import Router, Bot, F
from aiogram.types import Message, ChatPermissions
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

from utils import (
    is_admin, resolve_target, mention_html, parse_duration,
    mute_until_str, MUTE_PERMISSIONS, FULL_PERMISSIONS, bold, code
)
from database import (
    add_warn, get_warns, remove_warns, log_ban, log_mute,
    get_group, update_group_setting, upsert_group,
    add_required_channel, remove_required_channel, get_required_channels,
    add_filter, remove_filter, get_filters,
    save_note, get_note, get_all_notes, delete_note,
    add_blacklist_word, remove_blacklist_word, get_blacklist
)
from config import ADMIN_IDS

router = Router()

MAX_WARNS = 3  # auto-ban after 3 warns


def is_superadmin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ─── GUARD: only group admins can use these ───────────────────────────────────

async def admin_guard(message: Message, bot: Bot) -> bool:
    if message.chat.type == "private":
        await message.reply("❌ Bu buyruq faqat guruhda ishlaydi.")
        return False
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("❌ Faqat adminlar uchun!")
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════════════
#  /ban  —  ban user
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("ban"))
async def cmd_ban(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return

    args = message.text.split()[1:]
    uid, name, reason = await resolve_target(message, bot, args)

    if not uid:
        return await message.reply(
            "❓ Foydalanuvchini reply qiling yoki: <code>/ban @username sabab</code>"
        )

    if await is_admin(bot, message.chat.id, uid):
        return await message.reply("❌ Admin ban qilib bo'lmaydi!")

    try:
        await bot.ban_chat_member(message.chat.id, uid)
        await log_ban(message.chat.id, uid, message.from_user.id, reason)

        text = (
            f"🔨 <b>BAN</b>\n\n"
            f"👤 Foydalanuvchi: {mention_html(uid, name)}\n"
            f"👮 Admin: {mention_html(message.from_user.id, message.from_user.full_name)}\n"
        )
        if reason:
            text += f"📝 Sabab: {reason}\n"
        await message.reply(text)
    except TelegramBadRequest as e:
        await message.reply(f"❌ Xatolik: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  /unban
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("unban"))
async def cmd_unban(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return

    args = message.text.split()[1:]
    uid, name, _ = await resolve_target(message, bot, args)
    if not uid:
        return await message.reply("❓ Foydalanuvchini ko'rsating.")

    try:
        await bot.unban_chat_member(message.chat.id, uid, only_if_banned=True)
        await message.reply(
            f"✅ {mention_html(uid, name)} ban olib tashlandi!"
        )
    except TelegramBadRequest as e:
        await message.reply(f"❌ Xatolik: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  /kick  —  kick (unban so they can rejoin)
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("kick"))
async def cmd_kick(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return

    args = message.text.split()[1:]
    uid, name, reason = await resolve_target(message, bot, args)
    if not uid:
        return await message.reply("❓ Foydalanuvchini ko'rsating.")

    if await is_admin(bot, message.chat.id, uid):
        return await message.reply("❌ Admin kick qilib bo'lmaydi!")

    try:
        await bot.ban_chat_member(message.chat.id, uid)
        await bot.unban_chat_member(message.chat.id, uid)
        text = (
            f"👢 <b>KICK</b>\n\n"
            f"👤 Foydalanuvchi: {mention_html(uid, name)}\n"
            f"👮 Admin: {mention_html(message.from_user.id, message.from_user.full_name)}\n"
        )
        if reason:
            text += f"📝 Sabab: {reason}\n"
        await message.reply(text)
    except TelegramBadRequest as e:
        await message.reply(f"❌ Xatolik: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  /mute [duration] [reason]  —  mute user
#  Duration formats: 1m 2h 3d 1w  (minutes/hours/days/weeks)
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("mute"))
async def cmd_mute(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return

    parts = message.text.split()
    args = parts[1:]

    # Try to find duration in args
    duration = None
    duration_str = ""
    reason_parts = []

    uid, name, _ = await resolve_target(message, bot, [])

    if message.reply_to_message:
        uid = message.reply_to_message.from_user.id
        name = message.reply_to_message.from_user.full_name
        # remaining args = duration + reason
        for i, arg in enumerate(args):
            td, human = parse_duration(arg)
            if td and not duration:
                duration = td
                duration_str = human
            else:
                reason_parts.append(arg)
    else:
        if args:
            uid_arg = args[0]
            try:
                uid = int(uid_arg)
                member = await bot.get_chat_member(message.chat.id, uid)
                name = member.user.full_name
            except Exception:
                try:
                    chat = await bot.get_chat(f"@{uid_arg.lstrip('@')}")
                    uid = chat.id
                    name = chat.full_name or uid_arg
                except Exception:
                    return await message.reply("❓ Foydalanuvchi topilmadi.")
            for arg in args[1:]:
                td, human = parse_duration(arg)
                if td and not duration:
                    duration = td
                    duration_str = human
                else:
                    reason_parts.append(arg)

    if not uid:
        return await message.reply(
            "❓ Foydalanish: <code>/mute @user 2h sabab</code> yoki reply qiling"
        )

    if await is_admin(bot, message.chat.id, uid):
        return await message.reply("❌ Admin mute qilib bo'lmaydi!")

    reason = " ".join(reason_parts)

    try:
        if duration:
            until = datetime.now() + duration
            await bot.restrict_chat_member(
                message.chat.id, uid, MUTE_PERMISSIONS,
                until_date=until
            )
            until_str = mute_until_str(duration)
            await log_mute(message.chat.id, uid, message.from_user.id, duration_str, until_str, reason)
            time_text = f"⏱ Muddat: {duration_str}"
        else:
            await bot.restrict_chat_member(message.chat.id, uid, MUTE_PERMISSIONS)
            await log_mute(message.chat.id, uid, message.from_user.id, "doimiy", "doimiy", reason)
            time_text = "⏱ Muddat: Doimiy"

        text = (
            f"🔇 <b>MUTE</b>\n\n"
            f"👤 Foydalanuvchi: {mention_html(uid, name)}\n"
            f"👮 Admin: {mention_html(message.from_user.id, message.from_user.full_name)}\n"
            f"{time_text}\n"
        )
        if reason:
            text += f"📝 Sabab: {reason}\n"
        await message.reply(text)

    except TelegramBadRequest as e:
        await message.reply(f"❌ Xatolik: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  /unmute
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("unmute"))
async def cmd_unmute(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return

    args = message.text.split()[1:]
    uid, name, _ = await resolve_target(message, bot, args)
    if not uid:
        return await message.reply("❓ Foydalanuvchini ko'rsating.")

    try:
        await bot.restrict_chat_member(message.chat.id, uid, FULL_PERMISSIONS)
        await message.reply(
            f"🔊 {mention_html(uid, name)} mute olib tashlandi!"
        )
    except TelegramBadRequest as e:
        await message.reply(f"❌ Xatolik: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  /warn  —  warn user (auto-ban at MAX_WARNS)
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("warn"))
async def cmd_warn(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return

    args = message.text.split()[1:]
    uid, name, reason = await resolve_target(message, bot, args)
    if not uid:
        return await message.reply("❓ Foydalanuvchini ko'rsating.")

    if await is_admin(bot, message.chat.id, uid):
        return await message.reply("❌ Admin warn qilib bo'lmaydi!")

    count = await add_warn(message.chat.id, uid, message.from_user.id, reason)

    text = (
        f"⚠️ <b>OGOHLANTIRISH</b>\n\n"
        f"👤 Foydalanuvchi: {mention_html(uid, name)}\n"
        f"👮 Admin: {mention_html(message.from_user.id, message.from_user.full_name)}\n"
        f"📊 Ogohlantirish: {count}/{MAX_WARNS}\n"
    )
    if reason:
        text += f"📝 Sabab: {reason}\n"

    if count >= MAX_WARNS:
        try:
            await bot.ban_chat_member(message.chat.id, uid)
            await log_ban(message.chat.id, uid, message.from_user.id, f"Auto-ban: {MAX_WARNS} ogohlantirish")
            text += f"\n🔨 {MAX_WARNS} ta ogohlantirish — <b>AVTOMATIK BAN!</b>"
        except TelegramBadRequest:
            pass

    await message.reply(text)


# ═══════════════════════════════════════════════════════════════════════════════
#  /unwarn
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("unwarn"))
async def cmd_unwarn(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return

    args = message.text.split()[1:]
    uid, name, _ = await resolve_target(message, bot, args)
    if not uid:
        return await message.reply("❓ Foydalanuvchini ko'rsating.")

    await remove_warns(message.chat.id, uid)
    await message.reply(f"✅ {mention_html(uid, name)} barcha ogohlantirish tozalandi!")


# ═══════════════════════════════════════════════════════════════════════════════
#  /warns  —  check warns
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("warns"))
async def cmd_warns(message: Message, bot: Bot):
    if message.chat.type == "private":
        return

    args = message.text.split()[1:]
    uid, name, _ = await resolve_target(message, bot, args)
    if not uid:
        if message.reply_to_message:
            uid = message.reply_to_message.from_user.id
            name = message.reply_to_message.from_user.full_name
        else:
            uid = message.from_user.id
            name = message.from_user.full_name

    warns = await get_warns(message.chat.id, uid)
    if not warns:
        return await message.reply(f"✅ {mention_html(uid, name)} hech qanday ogohlantirish yo'q.")

    text = f"⚠️ {mention_html(uid, name)} — {len(warns)}/{MAX_WARNS} ogohlantirish:\n\n"
    for i, w in enumerate(warns, 1):
        reason = w['reason'] or "—"
        text += f"{i}. {w['warned_at'][:10]} — {reason}\n"
    await message.reply(text)


# ═══════════════════════════════════════════════════════════════════════════════
#  /admins  —  ping all admins
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("admins"))
async def cmd_admins(message: Message, bot: Bot):
    if message.chat.type == "private":
        return

    admins = await bot.get_chat_administrators(message.chat.id)
    text = "👮 <b>Guruh adminlari:</b>\n\n"
    mentions = []
    for admin in admins:
        if admin.user.is_bot:
            continue
        name = admin.user.full_name
        uid = admin.user.id
        title = f" [{admin.custom_title}]" if hasattr(admin, 'custom_title') and admin.custom_title else ""
        role = "👑 Egasi" if admin.status == "creator" else "⭐️ Admin"
        mentions.append(mention_html(uid, name))
        text += f"{role}: {mention_html(uid, name)}{title}\n"

    # Silent mention in a separate line so they all get notified
    if mentions:
        text += "\n" + " ".join(mentions)

    await message.reply(text)


# ═══════════════════════════════════════════════════════════════════════════════
#  /all  —  mention all members (uses admin list as proxy, warns about limits)
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("all"))
async def cmd_all(message: Message, bot: Bot):
    if message.chat.type == "private":
        return
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        return await message.reply("❌ Faqat adminlar /all ishlatishi mumkin!")

    args = message.text.split(maxsplit=1)
    custom_text = args[1] if len(args) > 1 else "E'tibor bering!"

    admins = await bot.get_chat_administrators(message.chat.id)
    mentions = []
    for admin in admins:
        if not admin.user.is_bot:
            mentions.append(mention_html(admin.user.id, admin.user.full_name))

    text = f"📢 <b>{custom_text}</b>\n\n"
    text += " ".join(mentions)
    await message.reply(text)


# ═══════════════════════════════════════════════════════════════════════════════
#  /pin  /unpin
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("pin"))
async def cmd_pin(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    if not message.reply_to_message:
        return await message.reply("❓ Pinlanadigan xabarga reply qiling.")
    try:
        await bot.pin_chat_message(message.chat.id, message.reply_to_message.message_id)
        await message.reply("📌 Xabar pinlandi!")
    except TelegramBadRequest as e:
        await message.reply(f"❌ Xatolik: {e}")


@router.message(Command("unpin"))
async def cmd_unpin(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    try:
        if message.reply_to_message:
            await bot.unpin_chat_message(message.chat.id, message.reply_to_message.message_id)
        else:
            await bot.unpin_chat_message(message.chat.id)
        await message.reply("📌 Xabar pin olib tashlandi!")
    except TelegramBadRequest as e:
        await message.reply(f"❌ Xatolik: {e}")


@router.message(Command("unpinall"))
async def cmd_unpinall(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    try:
        await bot.unpin_all_chat_messages(message.chat.id)
        await message.reply("✅ Barcha pin xabarlar olib tashlandi!")
    except TelegramBadRequest as e:
        await message.reply(f"❌ Xatolik: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  /settitle  /setdescription  /setphoto
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("settitle"))
async def cmd_settitle(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply("❓ Foydalanish: <code>/settitle Yangi nom</code>")
    try:
        await bot.set_chat_title(message.chat.id, args[1])
        await message.reply(f"✅ Guruh nomi o'zgartirildi: <b>{args[1]}</b>")
    except TelegramBadRequest as e:
        await message.reply(f"❌ Xatolik: {e}")


@router.message(Command("setdesc"))
async def cmd_setdesc(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    args = message.text.split(maxsplit=1)
    desc = args[1] if len(args) > 1 else ""
    try:
        await bot.set_chat_description(message.chat.id, desc)
        await message.reply("✅ Guruh tavsifi o'zgartirildi!")
    except TelegramBadRequest as e:
        await message.reply(f"❌ Xatolik: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  /setwelcome  /welcome  /delwelcome
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("setwelcome"))
async def cmd_setwelcome(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply(
            "❓ Foydalanish:\n<code>/setwelcome Xush kelibsiz {mention}! Sen #{number} a'zosan.</code>\n\n"
            "Teglар: {mention} {username} {number} {first_name} {chat_title}"
        )
    await update_group_setting(message.chat.id, "welcome_text", args[1])
    await update_group_setting(message.chat.id, "welcome_enabled", 1)
    await message.reply(f"✅ Xush kelish xabari o'rnatildi:\n\n{args[1]}")


@router.message(Command("delwelcome"))
async def cmd_delwelcome(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    await update_group_setting(message.chat.id, "welcome_enabled", 0)
    await message.reply("✅ Xush kelish xabari o'chirildi.")


@router.message(Command("welcome"))
async def cmd_welcome_toggle(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    group = await get_group(message.chat.id)
    if not group:
        return
    new_val = 0 if group["welcome_enabled"] else 1
    await update_group_setting(message.chat.id, "welcome_enabled", new_val)
    status = "yoqildi ✅" if new_val else "o'chirildi ❌"
    await message.reply(f"👋 Xush kelish xabari {status}.")


# ═══════════════════════════════════════════════════════════════════════════════
#  /setgoodbye  /goodbye
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("setgoodbye"))
async def cmd_setgoodbye(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply("❓ Foydalanish: <code>/setgoodbye {mention} guruhni tark etdi.</code>")
    await update_group_setting(message.chat.id, "welcome_text", args[1])
    await message.reply(f"✅ Xayrlashuv xabari o'rnatildi.")


@router.message(Command("goodbye"))
async def cmd_goodbye_toggle(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    group = await get_group(message.chat.id)
    if not group:
        return
    new_val = 0 if group["goodbye_enabled"] else 1
    await update_group_setting(message.chat.id, "goodbye_enabled", new_val)
    status = "yoqildi ✅" if new_val else "o'chirildi ❌"
    await message.reply(f"👋 Xayrlashuv xabari {status}.")


# ═══════════════════════════════════════════════════════════════════════════════
#  /antilink  /antiflood  toggle
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("antilink"))
async def cmd_antilink(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    group = await get_group(message.chat.id)
    if not group:
        return
    new_val = 0 if group["anti_link"] else 1
    await update_group_setting(message.chat.id, "anti_link", new_val)
    status = "yoqildi 🔗❌" if new_val else "o'chirildi ✅"
    await message.reply(f"Anti-link {status}.")


@router.message(Command("antiflood"))
async def cmd_antiflood(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    group = await get_group(message.chat.id)
    if not group:
        return
    new_val = 0 if group["anti_flood"] else 1
    await update_group_setting(message.chat.id, "anti_flood", new_val)
    status = "yoqildi 🌊❌" if new_val else "o'chirildi ✅"
    await message.reply(f"Anti-flood {status}.")


# ═══════════════════════════════════════════════════════════════════════════════
#  /addsub  /delsub  /listsub  —  mandatory subscription channels
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("addsub"))
async def cmd_addsub(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    args = message.text.split()[1:]
    if not args:
        return await message.reply("❓ Foydalanish: <code>/addsub @channel_username</code>")
    channel_username = args[0].lstrip("@")
    try:
        chat = await bot.get_chat(f"@{channel_username}")
        await add_required_channel(message.chat.id, chat.id, channel_username, chat.title)
        await message.reply(
            f"✅ <b>{chat.title}</b> majburiy obuna kanali qo'shildi!\n"
            f"🔗 @{channel_username}"
        )
    except Exception as e:
        await message.reply(f"❌ Kanal topilmadi: {e}")


@router.message(Command("delsub"))
async def cmd_delsub(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    args = message.text.split()[1:]
    if not args:
        return await message.reply("❓ Foydalanish: <code>/delsub @channel_username</code>")
    channel_username = args[0].lstrip("@")
    try:
        chat = await bot.get_chat(f"@{channel_username}")
        await remove_required_channel(message.chat.id, chat.id)
        await message.reply(f"✅ @{channel_username} majburiy obunadan olib tashlandi!")
    except Exception as e:
        await message.reply(f"❌ Xatolik: {e}")


@router.message(Command("listsub"))
async def cmd_listsub(message: Message, bot: Bot):
    if message.chat.type == "private":
        return
    channels = await get_required_channels(message.chat.id)
    if not channels:
        return await message.reply("📋 Majburiy obuna kanallari yo'q.")
    text = "📋 <b>Majburiy obuna kanallari:</b>\n\n"
    for i, ch in enumerate(channels, 1):
        text += f"{i}. <b>{ch['channel_title']}</b> — @{ch['channel_username']}\n"
    await message.reply(text)


# ═══════════════════════════════════════════════════════════════════════════════
#  /filter  /delfilter  /filters  — auto-reply keywords
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("filter"))
async def cmd_addfilter(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        return await message.reply("❓ Foydalanish: <code>/filter kalit_so'z javob matni</code>")
    keyword, response = parts[1].lower(), parts[2]
    await add_filter(message.chat.id, keyword, response)
    await message.reply(f"✅ Filter qo'shildi: <code>{keyword}</code>")


@router.message(Command("delfilter"))
async def cmd_delfilter(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("❓ Foydalanish: <code>/delfilter kalit_so'z</code>")
    keyword = parts[1].lower()
    await remove_filter(message.chat.id, keyword)
    await message.reply(f"✅ Filter o'chirildi: <code>{keyword}</code>")


@router.message(Command("filters"))
async def cmd_filters(message: Message, bot: Bot):
    if message.chat.type == "private":
        return
    filters = await get_filters(message.chat.id)
    if not filters:
        return await message.reply("📋 Filterlar yo'q.")
    text = "📋 <b>Filterlar:</b>\n\n"
    for f in filters:
        text += f"🔹 <code>{f['keyword']}</code>\n"
    await message.reply(text)


# ═══════════════════════════════════════════════════════════════════════════════
#  /save  /get  /notes  /delnote  — sticky notes
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("save"))
async def cmd_save(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        return await message.reply("❓ Foydalanish: <code>/save nom_matn</code>")
    name, content = parts[1].lower(), parts[2]
    await save_note(message.chat.id, name, content)
    await message.reply(f"✅ Eslatma saqlandi: <code>#{name}</code>")


@router.message(Command("get"))
async def cmd_get(message: Message, bot: Bot):
    if message.chat.type == "private":
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("❓ Foydalanish: <code>/get nom</code>")
    note = await get_note(message.chat.id, parts[1].lower())
    if not note:
        return await message.reply("❌ Eslatma topilmadi.")
    await message.reply(note["content"])


@router.message(Command("notes"))
async def cmd_notes(message: Message, bot: Bot):
    if message.chat.type == "private":
        return
    notes = await get_all_notes(message.chat.id)
    if not notes:
        return await message.reply("📋 Eslatmalar yo'q.")
    text = "📋 <b>Eslatmalar:</b>\n\n"
    for n in notes:
        text += f"📝 <code>#{n['name']}</code>\n"
    await message.reply(text)


@router.message(Command("delnote"))
async def cmd_delnote(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("❓ Foydalanish: <code>/delnote nom</code>")
    await delete_note(message.chat.id, parts[1].lower())
    await message.reply(f"✅ Eslatma o'chirildi.")


# ═══════════════════════════════════════════════════════════════════════════════
#  /addblacklist  /delblacklist  /blacklist
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("addblacklist"))
async def cmd_addblacklist(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("❓ Foydalanish: <code>/addblacklist so'z</code>")
    word = parts[1].lower()
    await add_blacklist_word(message.chat.id, word)
    await message.reply(f"🚫 Qora ro'yxatga qo'shildi: <code>{word}</code>")


@router.message(Command("delblacklist"))
async def cmd_delblacklist(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("❓ Foydalanish: <code>/delblacklist so'z</code>")
    word = parts[1].lower()
    await remove_blacklist_word(message.chat.id, word)
    await message.reply(f"✅ Qora ro'yxatdan olib tashlandi: <code>{word}</code>")


@router.message(Command("blacklist"))
async def cmd_blacklist_show(message: Message, bot: Bot):
    if message.chat.type == "private":
        return
    words = await get_blacklist(message.chat.id)
    if not words:
        return await message.reply("📋 Qora ro'yxat bo'sh.")
    text = "🚫 <b>Qora ro'yxat:</b>\n\n"
    text += " | ".join([f"<code>{w}</code>" for w in words])
    await message.reply(text)


# ═══════════════════════════════════════════════════════════════════════════════
#  /setrules  /rules
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("setrules"))
async def cmd_setrules(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("❓ Foydalanish: <code>/setrules Qoidalar matni...</code>")
    await update_group_setting(message.chat.id, "rules", parts[1])
    await message.reply("✅ Guruh qoidalari saqlandi!")


@router.message(Command("rules"))
async def cmd_rules(message: Message, bot: Bot):
    if message.chat.type == "private":
        return
    group = await get_group(message.chat.id)
    if not group or not group.get("rules"):
        return await message.reply("📋 Guruh qoidalari hali o'rnatilmagan.")
    await message.reply(f"📋 <b>Guruh qoidalari:</b>\n\n{group['rules']}")


# ═══════════════════════════════════════════════════════════════════════════════
#  /chatinfo  /userinfo  /id
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("chatinfo"))
async def cmd_chatinfo(message: Message, bot: Bot):
    if message.chat.type == "private":
        return
    chat = message.chat
    count = await bot.get_chat_member_count(chat.id)
    text = (
        f"ℹ️ <b>Guruh ma'lumotlari</b>\n\n"
        f"📛 Nomi: <b>{chat.title}</b>\n"
        f"🆔 ID: <code>{chat.id}</code>\n"
        f"👥 A'zolar: <b>{count}</b>\n"
        f"🔗 Username: @{chat.username or '—'}\n"
        f"📝 Tur: {chat.type}\n"
    )
    await message.reply(text)


@router.message(Command("userinfo"))
async def cmd_userinfo(message: Message, bot: Bot):
    user = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    member = None
    if message.chat.type != "private":
        try:
            member = await bot.get_chat_member(message.chat.id, user.id)
        except Exception:
            pass

    status = member.status if member else "—"
    text = (
        f"👤 <b>Foydalanuvchi ma'lumotlari</b>\n\n"
        f"📛 Ism: {mention_html(user.id, user.full_name)}\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"👤 Username: @{user.username or '—'}\n"
        f"🤖 Bot: {'Ha' if user.is_bot else 'Yo'q'}\n"
        f"📊 Status: {status}\n"
    )
    await message.reply(text)


@router.message(Command("id"))
async def cmd_id(message: Message, bot: Bot):
    if message.reply_to_message:
        user = message.reply_to_message.from_user
        await message.reply(
            f"👤 {mention_html(user.id, user.full_name)}\n"
            f"🆔 ID: <code>{user.id}</code>"
        )
    else:
        text = f"👤 Sizning ID: <code>{message.from_user.id}</code>\n"
        if message.chat.type != "private":
            text += f"💬 Guruh ID: <code>{message.chat.id}</code>"
        await message.reply(text)


# ═══════════════════════════════════════════════════════════════════════════════
#  /adminpanel  — text-based admin panel
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("adminpanel"))
async def cmd_adminpanel(message: Message, bot: Bot):
    if not await admin_guard(message, bot):
        return

    group = await get_group(message.chat.id)
    anti_link = "✅" if group and group.get("anti_link") else "❌"
    anti_flood = "✅" if group and group.get("anti_flood") else "❌"
    welcome = "✅" if group and group.get("welcome_enabled") else "❌"
    goodbye = "✅" if group and group.get("goodbye_enabled") else "❌"

    channels = await get_required_channels(message.chat.id)
    filters_list = await get_filters(message.chat.id)
    blacklist = await get_blacklist(message.chat.id)
    notes = await get_all_notes(message.chat.id)

    text = (
        f"⚙️ <b>Admin Panel — {message.chat.title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        f"🛡 <b>Moderatsiya buyruqlari:</b>\n"
        f"  /ban — foydalanuvchini ban qilish\n"
        f"  /unban — ban olish\n"
        f"  /kick — guruhdan chiqarish\n"
        f"  /mute 2h — jim qilish (1m/2h/3d/1w)\n"
        f"  /unmute — jim qilishni bekor\n"
        f"  /warn — ogohlantirish ({MAX_WARNS} ta = auto ban)\n"
        f"  /unwarn — ogohlantirishlarni tozalash\n"
        f"  /warns — ogohlantirishlarni ko'rish\n\n"

        f"📢 <b>Xabar buyruqlari:</b>\n"
        f"  /admins — adminlarni taglay\n"
        f"  /all <matn> — hammani taglay\n\n"

        f"📌 <b>Pin:</b>\n"
        f"  /pin /unpin /unpinall\n\n"

        f"🔧 <b>Sozlamalar:</b>\n"
        f"  Xush kelish: {welcome} — /welcome /setwelcome /delwelcome\n"
        f"  Xayrlashuv: {goodbye} — /goodbye /setgoodbye\n"
        f"  Anti-link: {anti_link} — /antilink\n"
        f"  Anti-flood: {anti_flood} — /antiflood\n\n"

        f"📡 <b>Majburiy obuna ({len(channels)} ta):</b>\n"
        f"  /addsub /delsub /listsub\n\n"

        f"🔍 <b>Filterlar ({len(filters_list)} ta):</b>\n"
        f"  /filter /delfilter /filters\n\n"

        f"🚫 <b>Qora ro'yxat ({len(blacklist)} ta so'z):</b>\n"
        f"  /addblacklist /delblacklist /blacklist\n\n"

        f"📝 <b>Eslatmalar ({len(notes)} ta):</b>\n"
        f"  /save /get /notes /delnote\n\n"

        f"📊 <b>Statistika:</b>\n"
        f"  /stats /top\n\n"

        f"ℹ️ <b>Ma'lumot:</b>\n"
        f"  /chatinfo /userinfo /id\n"
        f"  /rules /setrules\n"
        f"  /settitle /setdesc\n"
    )
    await message.reply(text)


# ═══════════════════════════════════════════════════════════════════════════════
#  /help
# ═══════════════════════════════════════════════════════════════════════════════
@router.message(Command("help"))
async def cmd_help(message: Message, bot: Bot):
    text = (
        "🤖 <b>Guruh boshqaruv boti — Buyruqlar</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👮 <b>Moderatsiya (admin):</b>\n"
        "/ban — Ban qilish\n"
        "/unban — Ban olib tashlash\n"
        "/kick — Guruhdan chiqarish\n"
        "/mute [vaqt] — Jim qilish (1m 2h 3d 1w)\n"
        "/unmute — Jim qilishni bekor\n"
        "/warn [sabab] — Ogohlantirish\n"
        "/unwarn — Ogohlantirishni tozalash\n"
        "/warns — Ogohlantirishlarni ko'rish\n\n"
        "📢 <b>Xabar (admin):</b>\n"
        "/admins — Adminlarni taglay\n"
        "/all [matn] — Hammani taglay\n\n"
        "📌 <b>Pin (admin):</b>\n"
        "/pin /unpin /unpinall\n\n"
        "🔧 <b>Sozlash (admin):</b>\n"
        "/setwelcome /delwelcome /welcome\n"
        "/setgoodbye /goodbye\n"
        "/antilink /antiflood\n"
        "/addsub /delsub /listsub\n"
        "/filter /delfilter /filters\n"
        "/addblacklist /delblacklist /blacklist\n"
        "/save /get /notes /delnote\n"
        "/setrules /settitle /setdesc\n\n"
        "📊 <b>Umumiy:</b>\n"
        "/rules — Qoidalar\n"
        "/stats — Statistika\n"
        "/top — Top foydalanuvchilar\n"
        "/chatinfo — Guruh ma'lumotlari\n"
        "/userinfo — Foydalanuvchi ma'lumotlari\n"
        "/id — ID ko'rish\n"
        "/adminpanel — Admin panel\n"
        "/help — Yordam\n"
    )
    await message.reply(text)
