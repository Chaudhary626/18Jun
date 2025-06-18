import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import ADMIN_IDS, PROOF_PATH, THUMB_PATH
import glob

def is_admin(uid):
    return uid in ADMIN_IDS

def build_main_menu(user):
    kb = []
    if not user:
        return InlineKeyboardMarkup([])
    kb = [
        [InlineKeyboardButton("🎬 Upload Video", callback_data="uploadvideo")],
        [InlineKeyboardButton("📂 My Videos", callback_data="myvideos")],
        [InlineKeyboardButton("✅ Ready for Task", callback_data="readytask")],
        [InlineKeyboardButton("🎯 My Task", callback_data="mytask")],
        [InlineKeyboardButton("⏸ Pause", callback_data="pause")],
        [InlineKeyboardButton("📊 Status", callback_data="status")],
    ]
    if is_admin(user['id']):
        kb.append([InlineKeyboardButton("👮 Admin Panel", callback_data="adminpanel")])
    return InlineKeyboardMarkup(kb)

def build_upload_menu():
    kb = [
        [InlineKeyboardButton("Cancel", callback_data="cancelupload")]
    ]
    return InlineKeyboardMarkup(kb)

def build_video_menu(video_id):
    kb = [
        [InlineKeyboardButton("❌ Remove Video", callback_data=f"removevideo:{video_id}")]
    ]
    return InlineKeyboardMarkup(kb)

def build_task_menu(task_id, proof_status, verify_status):
    kb = []
    if not proof_status:
        kb.append([InlineKeyboardButton("📤 Submit Proof", callback_data=f"submitproof:{task_id}")])
    if proof_status and not verify_status:
        kb.append([
            InlineKeyboardButton("✅ Approve", callback_data=f"review:{task_id}:approve"),
            InlineKeyboardButton("❌ Reject", callback_data=f"review:{task_id}:reject"),
            InlineKeyboardButton("🚩 Report", callback_data=f"review:{task_id}:report"),
        ])
    return InlineKeyboardMarkup(kb)

def build_admin_menu():
    kb = [
        [InlineKeyboardButton("👥 Users", callback_data="admin:users")],
        [InlineKeyboardButton("📝 Complaints", callback_data="admin:complaints")],
        [InlineKeyboardButton("⚠️ Strikes", callback_data="admin:strikes")],
        [InlineKeyboardButton("🔒 Ban/Unban", callback_data="admin:ban")],
        [InlineKeyboardButton("📊 Stats", callback_data="admin:stats")],
    ]
    return InlineKeyboardMarkup(kb)

async def send_long_message(update, text, parse_mode="HTML"):
    # Break long messages for Telegram limits
    chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode=parse_mode)

def cleanup_old_proofs():
    # Remove old proofs (files > 7 days old)
    files = glob.glob(os.path.join(PROOF_PATH, "*.mp4"))
    now = os.path.getmtime
    for f in files:
        if (os.path.getmtime(f) + 7*24*3600) < os.path.getmtime(f):
            try: os.remove(f)
            except: pass

def get_readable_time(dtstring):
    from datetime import datetime
    dt = datetime.fromisoformat(dtstring)
    return dt.strftime("%d %b %Y %H:%M")