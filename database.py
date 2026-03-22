import asyncpg
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=os.getenv("DATABASE_URL"),
            min_size=2,
            max_size=10,
            ssl="require"
        )
    return _pool


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                chat_id BIGINT PRIMARY KEY,
                title TEXT,
                username TEXT,
                member_count INTEGER DEFAULT 0,
                added_at TIMESTAMP DEFAULT NOW(),
                welcome_text TEXT,
                welcome_enabled INTEGER DEFAULT 1,
                goodbye_enabled INTEGER DEFAULT 1,
                anti_link INTEGER DEFAULT 0,
                anti_flood INTEGER DEFAULT 1,
                language TEXT DEFAULT 'uz',
                rules TEXT DEFAULT '',
                mute_new_members INTEGER DEFAULT 0,
                captcha_enabled INTEGER DEFAULT 0,
                log_channel_id BIGINT DEFAULT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                joined_at TIMESTAMP DEFAULT NOW(),
                is_blocked INTEGER DEFAULT 0,
                language TEXT DEFAULT 'uz'
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_members (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                user_id BIGINT,
                joined_at TIMESTAMP DEFAULT NOW(),
                message_count INTEGER DEFAULT 0,
                warn_count INTEGER DEFAULT 0,
                is_muted INTEGER DEFAULT 0,
                mute_until TIMESTAMP,
                UNIQUE(chat_id, user_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS warns (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                user_id BIGINT,
                admin_id BIGINT,
                reason TEXT,
                warned_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bans (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                user_id BIGINT,
                admin_id BIGINT,
                reason TEXT,
                banned_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mutes (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                user_id BIGINT,
                admin_id BIGINT,
                duration_text TEXT,
                mute_until TEXT,
                reason TEXT,
                muted_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS required_channels (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                channel_id BIGINT,
                channel_username TEXT,
                channel_title TEXT,
                added_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(chat_id, channel_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS filters (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                keyword TEXT,
                response TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                name TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(chat_id, name)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS message_stats (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                user_id BIGINT,
                date TEXT,
                count INTEGER DEFAULT 0,
                UNIQUE(chat_id, user_id, date)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                word TEXT,
                UNIQUE(chat_id, word)
            )
        """)
    logger.info("✅ PostgreSQL database initialized")


async def get_group(chat_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM groups WHERE chat_id=$1", chat_id)
        return dict(row) if row else None


async def upsert_group(chat_id: int, title: str, username: str = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO groups (chat_id, title, username) VALUES ($1,$2,$3)
            ON CONFLICT (chat_id) DO UPDATE SET title=EXCLUDED.title, username=EXCLUDED.username
        """, chat_id, title, username)


async def update_group_setting(chat_id: int, key: str, value):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(f"UPDATE groups SET {key}=$1 WHERE chat_id=$2", value, chat_id)


async def upsert_user(user_id: int, username: str, full_name: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, full_name) VALUES ($1,$2,$3)
            ON CONFLICT (user_id) DO UPDATE SET username=EXCLUDED.username, full_name=EXCLUDED.full_name
        """, user_id, username, full_name)


async def upsert_member(chat_id: int, user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO group_members (chat_id, user_id) VALUES ($1,$2)
            ON CONFLICT (chat_id, user_id) DO NOTHING
        """, chat_id, user_id)


async def increment_message_count(chat_id: int, user_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO message_stats (chat_id, user_id, date, count) VALUES ($1,$2,$3,1)
            ON CONFLICT (chat_id, user_id, date) DO UPDATE SET count = message_stats.count + 1
        """, chat_id, user_id, today)
        await conn.execute("""
            INSERT INTO group_members (chat_id, user_id) VALUES ($1,$2)
            ON CONFLICT (chat_id, user_id) DO UPDATE SET message_count = group_members.message_count + 1
        """, chat_id, user_id)


async def get_member(chat_id: int, user_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM group_members WHERE chat_id=$1 AND user_id=$2", chat_id, user_id)
        return dict(row) if row else None


async def add_warn(chat_id: int, user_id: int, admin_id: int, reason: str = "") -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO warns (chat_id, user_id, admin_id, reason) VALUES ($1,$2,$3,$4)",
            chat_id, user_id, admin_id, reason)
        await conn.execute(
            "UPDATE group_members SET warn_count=warn_count+1 WHERE chat_id=$1 AND user_id=$2",
            chat_id, user_id)
        return await conn.fetchval(
            "SELECT COUNT(*) FROM warns WHERE chat_id=$1 AND user_id=$2", chat_id, user_id)


async def get_warns(chat_id: int, user_id: int) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM warns WHERE chat_id=$1 AND user_id=$2 ORDER BY warned_at DESC",
            chat_id, user_id)
        return [dict(r) for r in rows]


async def remove_warns(chat_id: int, user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM warns WHERE chat_id=$1 AND user_id=$2", chat_id, user_id)
        await conn.execute(
            "UPDATE group_members SET warn_count=0 WHERE chat_id=$1 AND user_id=$2",
            chat_id, user_id)


async def log_ban(chat_id: int, user_id: int, admin_id: int, reason: str = ""):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO bans (chat_id, user_id, admin_id, reason) VALUES ($1,$2,$3,$4)",
            chat_id, user_id, admin_id, reason)


async def log_mute(chat_id: int, user_id: int, admin_id: int, duration_text: str, mute_until: str, reason: str = ""):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO mutes (chat_id, user_id, admin_id, duration_text, mute_until, reason) VALUES ($1,$2,$3,$4,$5,$6)",
            chat_id, user_id, admin_id, duration_text, mute_until, reason)


async def add_required_channel(chat_id: int, channel_id: int, channel_username: str, channel_title: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO required_channels (chat_id, channel_id, channel_username, channel_title)
            VALUES ($1,$2,$3,$4) ON CONFLICT (chat_id, channel_id) DO NOTHING
        """, chat_id, channel_id, channel_username, channel_title)


async def remove_required_channel(chat_id: int, channel_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM required_channels WHERE chat_id=$1 AND channel_id=$2", chat_id, channel_id)


async def get_required_channels(chat_id: int) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM required_channels WHERE chat_id=$1", chat_id)
        return [dict(r) for r in rows]


async def add_filter(chat_id: int, keyword: str, response: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO filters (chat_id, keyword, response) VALUES ($1,$2,$3)",
            chat_id, keyword, response)


async def remove_filter(chat_id: int, keyword: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM filters WHERE chat_id=$1 AND keyword=$2", chat_id, keyword)


async def get_filters(chat_id: int) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM filters WHERE chat_id=$1", chat_id)
        return [dict(r) for r in rows]


async def save_note(chat_id: int, name: str, content: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO notes (chat_id, name, content) VALUES ($1,$2,$3)
            ON CONFLICT (chat_id, name) DO UPDATE SET content=EXCLUDED.content
        """, chat_id, name, content)


async def get_note(chat_id: int, name: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM notes WHERE chat_id=$1 AND name=$2", chat_id, name)
        return dict(row) if row else None


async def get_all_notes(chat_id: int) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM notes WHERE chat_id=$1", chat_id)
        return [dict(r) for r in rows]


async def delete_note(chat_id: int, name: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM notes WHERE chat_id=$1 AND name=$2", chat_id, name)


async def add_blacklist_word(chat_id: int, word: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO blacklist (chat_id, word) VALUES ($1,$2) ON CONFLICT DO NOTHING",
            chat_id, word)


async def remove_blacklist_word(chat_id: int, word: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM blacklist WHERE chat_id=$1 AND word=$2", chat_id, word)


async def get_blacklist(chat_id: int) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT word FROM blacklist WHERE chat_id=$1", chat_id)
        return [r["word"] for r in rows]


async def get_top_members(chat_id: int, limit: int = 10) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT gm.user_id, gm.message_count, u.full_name, u.username
            FROM group_members gm
            LEFT JOIN users u ON u.user_id = gm.user_id
            WHERE gm.chat_id=$1
            ORDER BY gm.message_count DESC
            LIMIT $2
        """, chat_id, limit)
        return [dict(r) for r in rows]


async def get_group_stats(chat_id: int) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        members  = await conn.fetchval("SELECT COUNT(*) FROM group_members WHERE chat_id=$1", chat_id)
        bans     = await conn.fetchval("SELECT COUNT(*) FROM bans WHERE chat_id=$1", chat_id)
        warns    = await conn.fetchval("SELECT COUNT(*) FROM warns WHERE chat_id=$1", chat_id)
        mutes    = await conn.fetchval("SELECT COUNT(*) FROM mutes WHERE chat_id=$1", chat_id)
        messages = await conn.fetchval(
            "SELECT COALESCE(SUM(message_count),0) FROM group_members WHERE chat_id=$1", chat_id)
    return {"members": members, "bans": bans, "warns": warns, "mutes": mutes, "messages": messages}
