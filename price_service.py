"""
price_service.py — Narx olish moduli
Manbalar:
  - CBU (cbu.uz) — valyutalar (USD, EUR, RUB, GBP, JPY, CNY, KZT, ...)
  - metals-api.com bepul alternativ: frankfurter.app + manual gold fallback
  - CoinGecko — kriptovalyuta (BTC, ETH, USDT, BNB, SOL, TON, ...)
Kesh: 10 daqiqa (Railway da ham ishlaydi, xotira keshi)
"""

import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ─── KESH ────────────────────────────────────────────────────────────────────
_cache: dict = {}          # { key: (value, expires_at) }
CACHE_TTL = 600            # 10 daqiqa


def _cache_get(key: str):
    if key in _cache:
        val, exp = _cache[key]
        if datetime.now() < exp:
            return val
    return None


def _cache_set(key: str, val):
    _cache[key] = (val, datetime.now() + timedelta(seconds=CACHE_TTL))


# ─── CBU VALYUTALAR ──────────────────────────────────────────────────────────
CBU_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"

async def get_cbu_rates() -> dict[str, float]:
    """{'USD': 12800.0, 'EUR': 13900.0, ...} — 1 birlik = X so'm"""
    cached = _cache_get("cbu")
    if cached:
        return cached
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(CBU_URL, timeout=aiohttp.ClientTimeout(total=8)) as r:
                data = await r.json(content_type=None)
        rates = {}
        for item in data:
            code = item["Ccy"]
            rate = float(item["Rate"])
            nominal = float(item.get("Nominal", 1) or 1)
            rates[code] = rate / nominal   # 1 birlik narxi
        _cache_set("cbu", rates)
        logger.info(f"CBU: {len(rates)} valyuta yangilandi")
        return rates
    except Exception as e:
        logger.error(f"CBU xatolik: {e}")
        return {}


# ─── OLTIN / KUMUSH (gram, kg, tola) ─────────────────────────────────────────
# Frankfurter XAU (troy ounce, USD) → so'mga o'tkazamiz
FRANKFURTER_URL = "https://api.frankfurter.app/latest?from=XAU&to=USD"

TROY_OUNCE_GRAM = 31.1035     # 1 troy ounce = 31.1035 gram
TOLA_GRAM = 8.1               # 1 tola ≈ 8.1 gram (O'zbekiston tola)

async def get_gold_uzs() -> dict:
    """
    Qaytaradi:
      gram_usd  — 1 gram oltin USD da
      gram_uzs  — 1 gram oltin so'mda
      kg_uzs    — 1 kg oltin so'mda
      tola_uzs  — 1 tola oltin so'mda
      oz_usd    — 1 troy ounce USD da
    """
    cached = _cache_get("gold")
    if cached:
        return cached
    try:
        cbu = await get_cbu_rates()
        usd_uzs = cbu.get("USD", 0)
        if not usd_uzs:
            return {}

        async with aiohttp.ClientSession() as s:
            async with s.get(FRANKFURTER_URL, timeout=aiohttp.ClientTimeout(total=8)) as r:
                data = await r.json()

        # XAU → USD: 1 troy ounce = X USD
        oz_usd = data["rates"]["USD"]          # misol: 2350.0
        gram_usd = oz_usd / TROY_OUNCE_GRAM
        gram_uzs = gram_usd * usd_uzs
        kg_uzs = gram_uzs * 1000
        tola_uzs = gram_uzs * TOLA_GRAM

        result = {
            "gram_usd": round(gram_usd, 4),
            "gram_uzs": round(gram_uzs, 2),
            "kg_uzs":   round(kg_uzs, 2),
            "tola_uzs": round(tola_uzs, 2),
            "oz_usd":   round(oz_usd, 2),
        }
        _cache_set("gold", result)
        return result
    except Exception as e:
        logger.error(f"Gold xatolik: {e}")
        return {}


# ─── KUMUSH ───────────────────────────────────────────────────────────────────
SILVER_URL = "https://api.frankfurter.app/latest?from=XAG&to=USD"

async def get_silver_uzs() -> dict:
    cached = _cache_get("silver")
    if cached:
        return cached
    try:
        cbu = await get_cbu_rates()
        usd_uzs = cbu.get("USD", 0)
        if not usd_uzs:
            return {}

        async with aiohttp.ClientSession() as s:
            async with s.get(SILVER_URL, timeout=aiohttp.ClientTimeout(total=8)) as r:
                data = await r.json()

        oz_usd = data["rates"]["USD"]
        gram_usd = oz_usd / TROY_OUNCE_GRAM
        gram_uzs = gram_usd * usd_uzs

        result = {
            "gram_usd": round(gram_usd, 4),
            "gram_uzs": round(gram_uzs, 2),
            "kg_uzs":   round(gram_uzs * 1000, 2),
            "oz_usd":   round(oz_usd, 2),
        }
        _cache_set("silver", result)
        return result
    except Exception as e:
        logger.error(f"Silver xatolik: {e}")
        return {}


# ─── KRIPTOVALYUTA (CoinGecko — bepul) ───────────────────────────────────────
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
CRYPTO_IDS = {
    "BTC":  "bitcoin",
    "ETH":  "ethereum",
    "USDT": "tether",
    "BNB":  "binancecoin",
    "SOL":  "solana",
    "TON":  "the-open-network",
    "TRX":  "tron",
    "XRP":  "ripple",
    "ADA":  "cardano",
    "DOGE": "dogecoin",
    "MATIC":"matic-network",
    "DOT":  "polkadot",
    "LTC":  "litecoin",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "UNI":  "uniswap",
    "ATOM": "cosmos",
    "XLM":  "stellar",
    "NEAR": "near",
    "FIL":  "filecoin",
}

async def get_crypto_prices() -> dict[str, float]:
    """{'BTC': 68000.0, 'ETH': 3500.0, ...} — USD da"""
    cached = _cache_get("crypto")
    if cached:
        return cached
    try:
        ids = ",".join(CRYPTO_IDS.values())
        params = {"ids": ids, "vs_currencies": "usd"}
        async with aiohttp.ClientSession() as s:
            async with s.get(COINGECKO_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()

        result = {}
        for symbol, cg_id in CRYPTO_IDS.items():
            if cg_id in data:
                result[symbol] = data[cg_id]["usd"]
        _cache_set("crypto", result)
        logger.info(f"Crypto: {len(result)} ta yangilandi")
        return result
    except Exception as e:
        logger.error(f"Crypto xatolik: {e}")
        return {}


# ─── ASOSIY FUNKSIYA: so'rovni aniqlash va javob qaytarish ───────────────────

async def resolve_price_query(text: str) -> str | None:
    """
    Matndan narx so'rovini aniqlaydi va javob qaytaradi.
    None qaytarsa — narx so'rovi emas.
    """
    t = text.lower().strip()

    # Miqdor va birlik aniqlash (misol: "100 dollar", "5 ton", "2 gram oltin")
    amount, unit, asset = _parse_query(t)

    if not asset:
        return None

    return await _build_response(amount, unit, asset)


# ─── PARSER ──────────────────────────────────────────────────────────────────

import re

NUMBER_RE = re.compile(r"(\d+(?:[.,]\d+)?)")

# Valyuta sinonimlar
CURRENCY_ALIASES: dict[str, str] = {
    # USD
    "dollar": "USD", "dolar": "USD", "dollars": "USD",
    "usd": "USD", "$": "USD", "buck": "USD",
    # EUR
    "evro": "EUR", "euro": "EUR", "eur": "EUR", "€": "EUR",
    # RUB
    "rubl": "RUB", "rub": "RUB", "ruble": "RUB", "рубль": "RUB",
    # GBP
    "funt": "GBP", "pound": "GBP", "gbp": "GBP", "£": "GBP",
    # JPY
    "yen": "JPY", "yen": "JPY", "jpy": "JPY",
    # CNY
    "yuan": "CNY", "cny": "CNY", "rmb": "CNY",
    # KZT
    "tenge": "KZT", "kzt": "KZT",
    # AED
    "dirham": "AED", "aed": "AED",
    # TRY
    "lira": "TRY", "try": "TRY",
    # KRW
    "won": "KRW", "krw": "KRW",
    # CHF
    "frank": "CHF", "chf": "CHF",
    # GEL
    "lari": "GEL", "gel": "GEL",
    # UAH
    "grivna": "UAH", "uah": "UAH",
}

# Oltin/kumush sinonimlar
METAL_ALIASES: dict[str, str] = {
    "oltin": "GOLD", "gold": "GOLD", "au": "GOLD", "xau": "GOLD",
    "kumush": "SILVER", "silver": "SILVER", "ag": "SILVER", "xag": "SILVER",
}

# Og'irlik birliklar (gram ekvivalentida)
WEIGHT_UNITS: dict[str, float] = {
    "gram": 1, "gramm": 1, "gr": 1, "g": 1,
    "kg": 1000, "kilogram": 1000,
    "tola": 8.1, "тола": 8.1,
    "misqol": 4.8, "мискаль": 4.8,
    "oz": 31.1035, "ounce": 31.1035, "troy": 31.1035,
}

# Kripto sinonimlar
CRYPTO_ALIASES: dict[str, str] = {
    "bitcoin": "BTC", "btc": "BTC",
    "ethereum": "ETH", "eth": "ETH",
    "usdt": "USDT", "tether": "USDT",
    "bnb": "BNB", "binance": "BNB",
    "solana": "SOL", "sol": "SOL",
    "ton": "TON", "toncoin": "TON",
    "tron": "TRX", "trx": "TRX",
    "xrp": "XRP", "ripple": "XRP",
    "doge": "DOGE", "dogecoin": "DOGE",
    "ada": "ADA", "cardano": "ADA",
    "matic": "MATIC", "polygon": "MATIC",
    "dot": "DOT", "polkadot": "DOT",
    "ltc": "LTC", "litecoin": "LTC",
    "avax": "AVAX", "avalanche": "AVAX",
    "link": "LINK", "chainlink": "LINK",
    "uni": "UNI", "uniswap": "UNI",
    "atom": "ATOM", "cosmos": "ATOM",
    "xlm": "XLM", "stellar": "XLM",
    "near": "NEAR",
    "fil": "FIL", "filecoin": "FIL",
}


def _parse_query(text: str) -> tuple[float, str, str]:
    """
    Qaytaradi: (miqdor, og'irlik_birligi_yoki_'', aktiv_kodi)
    aktiv_kodi: 'USD' | 'GOLD' | 'BTC' | ...
    """
    # Raqam bor-yo'qligini tekshir
    num_match = NUMBER_RE.search(text)
    amount = float(num_match.group(1).replace(",", ".")) if num_match else 1.0

    # Kripto tekshir
    for alias, code in CRYPTO_ALIASES.items():
        if alias in text:
            # Og'irlik birliklarini e'tiborsiz qoldirish
            return amount, "", code

    # Oltin/kumush
    for alias, metal in METAL_ALIASES.items():
        if alias in text:
            # og'irlik birligi?
            weight_unit = ""
            grams = amount
            for wu, gval in WEIGHT_UNITS.items():
                if wu in text:
                    weight_unit = wu
                    grams = amount * gval
                    break
            # grams sonini amount sifatida qaytaramiz, unit="g_equivalent"
            return grams, "gram_eq", metal

    # Valyuta
    for alias, code in CURRENCY_ALIASES.items():
        if alias in text:
            return amount, "", code

    # Kod bo'yicha to'g'ridan-to'g'ri (misol: "100 eur uzs")
    words = text.split()
    for w in words:
        w_up = w.upper()
        if w_up in CURRENCY_ALIASES.values():
            return amount, "", w_up
        if w_up in CRYPTO_ALIASES.values():
            return amount, "", w_up

    return amount, "", ""


# ─── JAVOB YASASH ─────────────────────────────────────────────────────────────

def _fmt(num: float) -> str:
    """123456789.5 → '123 456 789,50'"""
    if num >= 1:
        int_part = int(num)
        dec_part = round((num - int_part) * 100)
        formatted = f"{int_part:,}".replace(",", " ")
        if dec_part:
            return f"{formatted},{dec_part:02d}"
        return formatted
    else:
        return f"{num:.6f}".rstrip("0").rstrip(".")


async def _build_response(amount: float, unit: str, asset: str) -> str | None:
    now_str = datetime.now().strftime("%H:%M")

    # ── KRIPTO ────────────────────────────────────────────────────────────────
    if asset in CRYPTO_ALIASES.values() or asset in [v for v in CRYPTO_ALIASES.values()]:
        prices = await get_crypto_prices()
        cbu = await get_cbu_rates()
        usd_uzs = cbu.get("USD", 0)

        if asset not in prices or not usd_uzs:
            return f"❌ {asset} narxi topilmadi."

        price_usd = prices[asset]
        total_usd = price_usd * amount
        total_uzs = total_usd * usd_uzs

        label = f"{_fmt(amount)} {asset}" if amount != 1 else asset
        return (
            f"💎 <b>{label}</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💵 1 {asset} = <b>{_fmt(price_usd)} USD</b>\n"
            f"💴 1 {asset} = <b>{_fmt(price_usd * usd_uzs)} so'm</b>\n"
        ) + (
            f"\n📊 {_fmt(amount)} {asset}:\n"
            f"  = <b>{_fmt(total_usd)} USD</b>\n"
            f"  = <b>{_fmt(total_uzs)} so'm</b>\n"
            if amount != 1 else ""
        ) + f"\n🕐 {now_str} (CBU + CoinGecko)"

    # ── OLTIN ─────────────────────────────────────────────────────────────────
    if asset == "GOLD":
        gold = await get_gold_uzs()
        if not gold:
            return "❌ Oltin narxi topilmadi."

        gram_uzs = gold["gram_uzs"]
        total_uzs = gram_uzs * amount   # amount = gram ekvivalenti

        # Birliklarni aniqlashtirish
        if amount == 1:
            label = "1 gram oltin"
        elif amount == 1000:
            label = "1 kg oltin"
        elif amount == 8.1:
            label = "1 tola oltin"
        elif amount == 31.1035:
            label = "1 troy ounce oltin"
        else:
            label = f"{_fmt(amount)} gram oltin"

        return (
            f"🥇 <b>{label}</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"  = <b>{_fmt(total_uzs)} so'm</b>\n"
            f"  = <b>{_fmt(total_uzs / gold['gram_uzs'] * gold['gram_usd'])} USD</b>\n\n"
            f"📈 Bozor: 1 oz = {_fmt(gold['oz_usd'])} USD\n"
            f"🕐 {now_str} (CBU + Frankfurter)"
        )

    # ── KUMUSH ────────────────────────────────────────────────────────────────
    if asset == "SILVER":
        silver = await get_silver_uzs()
        if not silver:
            return "❌ Kumush narxi topilmadi."

        gram_uzs = silver["gram_uzs"]
        total_uzs = gram_uzs * amount

        if amount == 1:
            label = "1 gram kumush"
        elif amount == 1000:
            label = "1 kg kumush"
        else:
            label = f"{_fmt(amount)} gram kumush"

        return (
            f"🥈 <b>{label}</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"  = <b>{_fmt(total_uzs)} so'm</b>\n"
            f"  = <b>{_fmt(total_uzs / gram_uzs * silver['gram_usd'])} USD</b>\n\n"
            f"📈 Bozor: 1 oz = {_fmt(silver['oz_usd'])} USD\n"
            f"🕐 {now_str} (CBU + Frankfurter)"
        )

    # ── VALYUTA ───────────────────────────────────────────────────────────────
    cbu = await get_cbu_rates()
    if asset not in cbu:
        return None

    rate = cbu[asset]       # 1 birlik = X so'm
    total_uzs = rate * amount
    label = f"{_fmt(amount)} {asset}" if amount != 1 else f"1 {asset}"

    return (
        f"💱 <b>{label}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"  = <b>{_fmt(total_uzs)} so'm</b>\n\n"
        f"📊 1 {asset} = {_fmt(rate)} so'm\n"
        f"🕐 {now_str} (CBU rasmiy kurs)"
    )
