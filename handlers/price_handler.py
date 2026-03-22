import re
import aiohttp
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Router, Bot, F
from aiogram.types import Message

router = Router()
logger = logging.getLogger(__name__)

# ─── CACHE (10 daqiqa) ────────────────────────────────────────────────────────
_cache: dict = {}
CACHE_TTL = 600  # seconds


def cached(key: str, value=None):
    if value is not None:
        _cache[key] = {"value": value, "ts": datetime.now()}
        return value
    entry = _cache.get(key)
    if entry and (datetime.now() - entry["ts"]).seconds < CACHE_TTL:
        return entry["value"]
    return None


# ─── KALIT SO'ZLAR ────────────────────────────────────────────────────────────
# har bir valyuta/tovar uchun o'zbek/rus/ingliz so'zlar

TRIGGERS = {
    "USD": {
        "keys": ["dollar", "usd", "долл", "бакс", "$"],
        "label": "🇺🇸 Dollar",
        "fetch": "cbu_usd",
    },
    "EUR": {
        "keys": ["euro", "eur", "евро", "yevro", "€"],
        "label": "🇪🇺 Evro",
        "fetch": "cbu_eur",
    },
    "RUB": {
        "keys": ["rubl", "ruble", "rub", "рубл", "rubll"],
        "label": "🇷🇺 Rubl",
        "fetch": "cbu_rub",
    },
    "GBP": {
        "keys": ["funt", "pound", "gbp", "фунт", "£"],
        "label": "🇬🇧 Funt",
        "fetch": "cbu_gbp",
    },
    "CNY": {
        "keys": ["yuan", " yuan", "cny", "юань", "xitoy"],
        "label": "🇨🇳 Yuan",
        "fetch": "cbu_cny",
    },
    "KZT": {
        "keys": ["tenge", "kzt", "тенге", "qozoq"],
        "label": "🇰🇿 Tenge",
        "fetch": "cbu_kzt",
    },
    "TRY": {
        "keys": ["lira", "try", "лира", "turk"],
        "label": "🇹🇷 Lira",
        "fetch": "cbu_try",
    },
    "AED": {
        "keys": ["dirham", "aed", "дирхам", "dubai"],
        "label": "🇦🇪 Dirham",
        "fetch": "cbu_aed",
    },
    "JPY": {
        "keys": ["yen", "jpy", "иена", "yapon"],
        "label": "🇯🇵 Yen",
        "fetch": "cbu_jpy",
    },
    "XAU_G": {
        "keys": ["gold", "oltin", "золото", "xau", "gram oltin", "1g oltin", "oltin gram"],
        "label": "🥇 Oltin (1 gram)",
        "fetch": "gold_gram",
    },
    "XAU_OZ": {
        "keys": ["troy", "untsiya", "ounce", "oz oltin"],
        "label": "🥇 Oltin (1 troy oz)",
        "fetch": "gold_oz",
    },
    "XAG_G": {
        "keys": ["kumush", "silver", "xag", "серебро"],
        "label": "🥈 Kumush (1 gram)",
        "fetch": "silver_gram",
    },
    "BTC": {
        "keys": ["bitcoin", "btc", "биткоин"],
        "label": "₿ Bitcoin",
        "fetch": "crypto_btc",
    },
    "ETH": {
        "keys": ["ethereum", "eth", "эфир", "efir"],
        "label": "⟠ Ethereum",
        "fetch": "crypto_eth",
    },
    "BNB": {
        "keys": ["bnb", "binance coin"],
        "label": "🔶 BNB",
        "fetch": "crypto_bnb",
    },
    "USDT": {
        "keys": ["usdt", "tether", "tezar"],
        "label": "💵 USDT (Tether)",
        "fetch": "crypto_usdt",
    },
    "TON": {
        "keys": ["ton coin", "toncoin", " ton ", "ton narx", "ton usd", "ton uzs", "ton kurs"],
        "label": "💎 TON Coin",
        "fetch": "crypto_ton",
    },
    "SOL": {
        "keys": ["solana", "sol"],
        "label": "◎ Solana",
        "fetch": "crypto_sol",
    },
    "DOGE": {
        "keys": ["dogecoin", "doge"],
        "label": "🐶 Dogecoin",
        "fetch": "crypto_doge",
    },
}

# Miqdor topish (1 dollar, 100 evro, 0.5 btc)
AMOUNT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*", re.IGNORECASE)


def find_amount(text: str) -> float:
    m = AMOUNT_RE.search(text)
    if m:
        return float(m.group(1).replace(",", "."))
    return 1.0


def detect_asset(text: str) -> str | None:
    text_lower = text.lower()
    for code, info in TRIGGERS.items():
        for kw in info["keys"]:
            if kw in text_lower:
                return code
    return None


# ─── API FETCHERS ─────────────────────────────────────────────────────────────

async def fetch_cbu_rates() -> dict:
    """CBU.uz dan barcha valyutalar kursi (UZS da)"""
    cached_val = cached("cbu_all")
    if cached_val:
        return cached_val

    url = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                data = await resp.json(content_type=None)
                rates = {}
                for item in data:
                    code = item["Ccy"].upper()
                    rate = float(item["Rate"])
                    nominal = float(item.get("Nominal", 1))
                    rates[code] = rate / nominal  # UZS per 1 unit
                cached("cbu_all", rates)
                return rates
    except Exception as e:
        logger.error(f"CBU API error: {e}")
        return {}


async def fetch_gold_usd() -> tuple[float, float]:
    """Oltin va kumush narxi USD/oz — metals.live (bepul, CORS yo'q)"""
    cached_val = cached("metals_usd")
    if cached_val:
        return cached_val

    # metals.live bepul JSON
    url = "https://metals.live/api/spot"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                data = await resp.json(content_type=None)
                gold_oz = None
                silver_oz = None
                for item in data:
                    if isinstance(item, dict):
                        if item.get("metal") == "XAU" or "gold" in str(item.get("symbol","")).lower():
                            gold_oz = float(item.get("price", 0))
                        if item.get("metal") == "XAG" or "silver" in str(item.get("symbol","")).lower():
                            silver_oz = float(item.get("price", 0))
                if not gold_oz:
                    raise ValueError("No gold data")
                result = (gold_oz or 0, silver_oz or 0)
                cached("metals_usd", result)
                return result
    except Exception:
        pass

    # Fallback: frankfurter.app (ECB based, oltin yo'q lekin valyuta bor)
    # Ikkinchi fallback: coinbase rates API
    try:
        url2 = "https://api.coinbase.com/v2/exchange-rates?currency=XAU"
        async with aiohttp.ClientSession() as session:
            async with session.get(url2, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                data = await resp.json()
                usd_per_xau = 1 / float(data["data"]["rates"]["USD"])
                # XAG ham olish
                url3 = "https://api.coinbase.com/v2/exchange-rates?currency=XAG"
                async with session.get(url3, timeout=aiohttp.ClientTimeout(total=8)) as resp3:
                    data3 = await resp3.json()
                    usd_per_xag = 1 / float(data3["data"]["rates"]["USD"])
                result = (usd_per_xau, usd_per_xag)
                cached("metals_usd", result)
                return result
    except Exception as e:
        logger.error(f"Metals API error: {e}")
        return (0, 0)


async def fetch_crypto_uzs(coin_id: str, usd_rate: float) -> float:
    """CoinGecko bepul API — kripto narxi UZS da"""
    cache_key = f"crypto_{coin_id}"
    cached_val = cached(cache_key)
    if cached_val:
        return cached_val

    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                usd_price = data[coin_id]["usd"]
                uzs_price = usd_price * usd_rate
                cached(cache_key, uzs_price)
                return uzs_price
    except Exception as e:
        logger.error(f"CoinGecko error ({coin_id}): {e}")
        return 0


COINGECKO_IDS = {
    "crypto_btc": "bitcoin",
    "crypto_eth": "ethereum",
    "crypto_bnb": "binancecoin",
    "crypto_usdt": "tether",
    "crypto_ton": "the-open-network",
    "crypto_sol": "solana",
    "crypto_doge": "dogecoin",
}

TROY_OZ_IN_GRAMS = 31.1035


async def get_price_uzs(fetch_key: str) -> tuple[float, str]:
    """
    Returns (price_in_uzs_per_1_unit, source_label)
    """
    cbu = await fetch_cbu_rates()
    usd_rate = cbu.get("USD", 12700)

    # ── CBU valyutalar ────────────────────────────────────────
    cbu_map = {
        "cbu_usd": "USD",
        "cbu_eur": "EUR",
        "cbu_rub": "RUB",
        "cbu_gbp": "GBP",
        "cbu_cny": "CNY",
        "cbu_kzt": "KZT",
        "cbu_try": "TRY",
        "cbu_aed": "AED",
        "cbu_jpy": "JPY",
    }
    if fetch_key in cbu_map:
        code = cbu_map[fetch_key]
        return cbu.get(code, 0), "CBU.uz"

    # ── Oltin ─────────────────────────────────────────────────
    if fetch_key in ("gold_gram", "gold_oz", "silver_gram"):
        gold_oz_usd, silver_oz_usd = await fetch_gold_usd()
        if fetch_key == "gold_gram":
            return (gold_oz_usd / TROY_OZ_IN_GRAMS) * usd_rate, "metals.live"
        elif fetch_key == "gold_oz":
            return gold_oz_usd * usd_rate, "metals.live"
        elif fetch_key == "silver_gram":
            return (silver_oz_usd / TROY_OZ_IN_GRAMS) * usd_rate, "metals.live"

    # ── Kripto ────────────────────────────────────────────────
    if fetch_key in COINGECKO_IDS:
        coin_id = COINGECKO_IDS[fetch_key]
        uzs = await fetch_crypto_uzs(coin_id, usd_rate)
        return uzs, "CoinGecko"

    return 0, "N/A"


def format_uzs(amount: float) -> str:
    """12349000.5  →  12 349 000 so'm"""
    rounded = round(amount)
    return f"{rounded:,}".replace(",", " ") + " so'm"


def format_price_message(asset_code: str, amount: float, price_uzs: float, source: str) -> str:
    info = TRIGGERS[asset_code]
    label = info["label"]
    total = price_uzs * amount
    now = datetime.now().strftime("%H:%M:%S")

    if amount == 1:
        amount_str = f"1 {label}"
    else:
        # Miqdor chiroyli ko'rsatish
        if amount == int(amount):
            amount_str = f"{int(amount)} {label}"
        else:
            amount_str = f"{amount} {label}"

    lines = [
        f"💰 <b>{amount_str}</b>",
        f"",
        f"📊 Narx: <b>{format_uzs(price_uzs)}</b>",
    ]
    if amount != 1:
        lines.append(f"🧮 Jami: <b>{format_uzs(total)}</b>")

    lines += [
        f"",
        f"🕐 {now} | 📡 {source}",
        f"<i>⚡️ Narxlar 10 daqiqada bir yangilanadi</i>"
    ]
    return "\n".join(lines)


# ─── MESSAGE HANDLER ─────────────────────────────────────────────────────────

@router.message(F.text)
async def price_detector(message: Message, bot: Bot):
    if not message.text or message.chat.type == "private":
        return

    text = message.text
    asset_code = detect_asset(text)
    if not asset_code:
        return

    info = TRIGGERS[asset_code]
    amount = find_amount(text)

    # Xabar yuborish uchun "typing" ko'rsatish
    await bot.send_chat_action(message.chat.id, "typing")

    price_uzs, source = await get_price_uzs(info["fetch"])

    if price_uzs <= 0:
        await message.reply("⚠️ Narxni olishda xatolik. Keyinroq urinib ko'ring.")
        return

    text_out = format_price_message(asset_code, amount, price_uzs, source)
    await message.reply(text_out)
