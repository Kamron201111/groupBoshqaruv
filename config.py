import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "123456789").split(",")))

# Anti-flood settings
FLOOD_LIMIT = 5
FLOOD_TIME = 10
FLOOD_MUTE_DURATION = 300

# Anti-link
ANTI_LINK_ENABLED = True

# Welcome default
DEFAULT_WELCOME = "👋 Xush kelibsiz, {mention}! #{number} a'zo sifatida qo'shildingiz."

# Bot version
BOT_VERSION = "2.0.0"
