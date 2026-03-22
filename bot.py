import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from database import init_db
from handlers import (
    admin_handler,
    user_handler,
    subscription_handler,
    warn_handler,
    mute_handler,
    stats_handler,
    welcome_handler,
    antiflood_handler,
    antilink_handler,
    price_handler,
)
from middlewares.subscription import SubscriptionMiddleware
from middlewares.flood import FloodMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    await init_db()

    bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Middlewares
    dp.message.middleware(FloodMiddleware())
    dp.message.middleware(SubscriptionMiddleware(bot))

    # Routers — price_handler oldin (admin_handler dan avval tekshirilsin)
    dp.include_router(admin_handler.router)
    dp.include_router(subscription_handler.router)
    dp.include_router(warn_handler.router)
    dp.include_router(mute_handler.router)
    dp.include_router(stats_handler.router)
    dp.include_router(welcome_handler.router)
    dp.include_router(antiflood_handler.router)
    dp.include_router(antilink_handler.router)
    dp.include_router(price_handler.router)   # ← YANGI
    dp.include_router(user_handler.router)    # eng oxirgi

    logger.info("🤖 Bot ishga tushdi!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
