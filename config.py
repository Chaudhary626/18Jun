import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "123456789").split(",")]
DB_PATH = os.getenv("DB_PATH", "bot.db")
PROOF_PATH = os.getenv("PROOF_PATH", "proofs/")
THUMB_PATH = os.getenv("THUMB_PATH", "thumbs/")

os.makedirs(PROOF_PATH, exist_ok=True)
os.makedirs(THUMB_PATH, exist_ok=True)