import asyncio
import logging
import os
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, InputFile
)
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler,
    filters, CallbackQueryHandler, ConversationHandler
)
from config import BOT_TOKEN, ADMIN_IDS, PROOF_PATH, THUMB_PATH
from db import (
    init_db, add_user, get_user, get_user_active_video_count, add_video, get_videos_by_user,
    get_ready_users, create_task_pair, get_task_for_user, submit_proof, verify_proof,
    get_video_by_id, get_task_by_id, set_user_paused, set_user_active, remove_video,
    get_complaints, add_complaint, get_all_tasks, admin_ban_user, admin_strike_user,
    admin_unban_user, admin_remove_strike, get_pending_tasks_timeout,
    get_all_users, get_user_tasks, set_task_status, get_user_strikes,
    get_user_ban_status, get_user_pause_status, get_admin_stats
)
from utils import (
    is_admin, build_main_menu, build_upload_menu, build_video_menu,
    build_task_menu, build_admin_menu, send_long_message, cleanup_old_proofs,
    get_readable_time
)
from datetime import datetime, timedelta

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- States for ConversationHandler ---
UPLOAD_TITLE, UPLOAD_THUMB, UPLOAD_LINK, UPLOAD_DURATION = range(4)
SUBMIT_PROOF = 10
REPORT_REASON = 20

# --- Utility: Async Cleanup Job for Timeouts ---
async def timeout_job(app: Application):
    while True:
        await asyncio.sleep(180)  # 3 min
        timeouts = get_pending_tasks_timeout()
        for task in timeouts:
            # Check which user is delaying and apply anti-cheat logic
            task_id, user_a, user_b, proof_a, proof_b, verify_a, verify_b, created = task
            now = datetime.now()
            created_dt = datetime.fromisoformat(created)
            timeout_limit = timedelta(hours=2)
            # If proof_a submitted but verify_b delayed
            if proof_a and not verify_b and (now - created_dt) > timeout_limit:
                admin_strike_user(user_b)
                set_task_status(task_id, f"auto_a_eligible")
            # If proof_b submitted but verify_a delayed
            if proof_b and not verify_a and (now - created_dt) > timeout_limit:
                admin_strike_user(user_a)
                set_task_status(task_id, f"auto_b_eligible")
        # Also cleanup old proofs
        cleanup_old_proofs()

# --- Start and Help ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user)
    await update.message.reply_text(
        f"👋 Namaste {user.mention_html()}! Yeh bot YouTube mutual engagement ke liye hai.\n"
        "Koi bhi galat kaam, cheating ya inactivity par penalty hai.\n\n"
        "Menu se continue karein 👇",
        reply_markup=build_main_menu(get_user(user.id)), parse_mode="HTML"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_long_message(
        update, 
        "📋 <b>Bot Rules & Flow:</b>\n"
        "1️⃣ Apni YouTube video upload karein (title, thumbnail, link, duration)\n"
        "2️⃣ Jab ready ho, 'Ready' dabaye. Pairing ke baad aapko kisi ki video milegi dekhne ko.\n"
        "3️⃣ Video instructions ke hisab se dekhein. Screen record karein poora process.\n"
        "4️⃣ Proof upload karein. Pair ka proof approve/reject bhi karein.\n"
        "5️⃣ Galat/fake proof ya cheating par 'Report to Admin' karein.\n"
        "6️⃣ Agar pair inactive/delay karta hai, system aapko aage le jayega, cheater ko warning/strike.\n"
        "7️⃣ /pause se break le sakte hain (pending task na ho toh).\n"
        "8️⃣ /status se apni progress dekhein.\n"
        "⚠️ 3 strike = ban, admin ke pass full control hai."
        "\n\nAapka experience fair aur transparent rahega! 🎯", parse_mode="HTML"
    )

# --- Main Menu Handler ---
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user)
    await update.message.reply_text(
        "👇 Main Menu", reply_markup=build_main_menu(get_user(user.id))
    )

# --- Video Upload Conversation ---
async def upload_video_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if get_user_active_video_count(user.id) >= 5:
        await update.message.reply_text(
            "🚫 Maximum 5 active videos allowed. Remove old video to upload new."
        )
        return ConversationHandler.END
    await update.message.reply_text(
        "🎬 <b>Step 1/4</b>\nSend your YouTube video <b>title</b>:",
        parse_mode="HTML", reply_markup=ReplyKeyboardRemove()
    )
    return UPLOAD_TITLE

async def upload_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['video_title'] = update.message.text.strip()
    await update.message.reply_text(
        "🖼 <b>Step 2/4</b>\nSend your video <b>thumbnail</b> (as photo):",
        parse_mode="HTML"
    )
    return UPLOAD_THUMB

async def upload_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❗Thumbnail photo required.")
        return UPLOAD_THUMB
    file = await update.message.photo[-1].get_file()
    file_path = os.path.join(THUMB_PATH, f"{update.effective_user.id}_{datetime.now().timestamp()}.jpg")
    await file.download_to_drive(file_path)
    context.user_data['video_thumb'] = file_path
    await update.message.reply_text(
        "🔗 <b>Step 3/4</b>\nSend your YouTube video <b>link</b> (or type 'skip'):",
        parse_mode="HTML"
    )
    return UPLOAD_LINK

async def upload_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    if link.lower() == "skip":
        link = ""
    context.user_data['video_link'] = link
    await update.message.reply_text(
        "⏱ <b>Step 4/4</b>\nSend video <b>duration in seconds</b> (max 300):",
        parse_mode="HTML"
    )
    return UPLOAD_DURATION

async def upload_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        duration = int(update.message.text.strip())
        if duration < 30 or duration > 300:
            raise ValueError
        context.user_data['video_duration'] = duration
    except Exception:
        await update.message.reply_text("❗Enter valid duration (30-300 seconds).")
        return UPLOAD_DURATION
    user = update.effective_user
    add_video(
        user.id,
        context.user_data['video_title'],
        context.user_data['video_link'],
        context.user_data['video_thumb'],
        context.user_data['video_duration']
    )
    await update.message.reply_text(
        "✅ Video uploaded! Check your active videos in menu.",
        reply_markup=build_main_menu(get_user(user.id))
    )
    return ConversationHandler.END

async def upload_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.", reply_markup=build_main_menu(get_user(update.effective_user.id)))
    return ConversationHandler.END

# --- Show My Videos ---
async def my_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    videos = get_videos_by_user(user.id)
    if not videos:
        await update.message.reply_text("❌ No active videos found.")
        return
    for v in videos:
        msg = f"🎬 <b>{v['title']}</b>\n"
        if v['yt_link']:
            msg += f"🔗 {v['yt_link']}\n"
        msg += f"⏱ {v['duration']} sec"
        kb = build_video_menu(v['id'])
        await update.message.reply_photo(
            InputFile(v['thumb']), caption=msg, parse_mode="HTML", reply_markup=kb
        )

async def remove_video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    video_id = int(query.data.split(":")[1])
    video = get_video_by_id(video_id)
    if not video or video['user_id'] != query.from_user.id:
        await query.answer("Not allowed.", show_alert=True)
        return
    remove_video(video_id)
    await query.answer("✅ Video removed.", show_alert=True)
    await query.edit_message_caption("❌ Video removed.")

# --- Pause/Resume ---
async def pause_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    set_user_paused(user.id)
    await update.message.reply_text("⏸ You are now paused. Use /resume to activate.", reply_markup=build_main_menu(get_user(user.id)))

async def resume_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    set_user_active(user.id)
    await update.message.reply_text("▶️ You are now active!", reply_markup=build_main_menu(get_user(user.id)))

# --- Status Check ---
async def status_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    strikes = get_user_strikes(user.id)
    banned = get_user_ban_status(user.id)
    paused = get_user_pause_status(user.id)
    tasks = get_user_tasks(user.id)
    msg = f"👤 <b>Status for {user.mention_html()}</b>\n"
    msg += f"Strikes: <b>{strikes}</b>\n"
    msg += f"Banned: <b>{'Yes' if banned else 'No'}</b>\n"
    msg += f"Paused: <b>{'Yes' if paused else 'No'}</b>\n"
    msg += f"Total Tasks: <b>{len(tasks)}</b>\n"
    await update.message.reply_text(msg, parse_mode="HTML")

# --- Ready for Task / Pairing ---
async def ready_for_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user)
    # Try to pair user if possible
    paired, partner, task_id = create_task_pair(user.id)
    if paired:
        # Notify both users
        partner_user = get_user(partner)
        await update.message.reply_text(
            f"🤝 Paired with <b>{partner_user['username']}</b>!\n"
            "Check your assigned video in menu.", parse_mode="HTML"
        )
        # Optionally, send assigned video info here
    else:
        await update.message.reply_text("⏳ Waiting for another user...")

# --- My Task / Assigned Video Details ---
async def my_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    task = get_task_for_user(user.id)
    if not task:
        await update.message.reply_text("❌ No current task. Use 'Ready' in menu.")
        return
    # Determine assigned video & partner
    if user.id == task['user_a']:
        partner_id = task['user_b']
        assigned_video_id = task['video_b_id']
        proof_status = task['proof_a']
        verify_status = task['verify_a']
    else:
        partner_id = task['user_a']
        assigned_video_id = task['video_a_id']
        proof_status = task['proof_b']
        verify_status = task['verify_b']
    video = get_video_by_id(assigned_video_id)
    partner = get_user(partner_id)
    msg = (f"🎯 <b>Your Task</b>\n"
           f"You must watch <b>{partner['username']}</b>'s video:\n"
           f"🎬 <b>{video['title']}</b>\n"
           f"Duration: <b>{video['duration']} sec</b>\n")
    if video['yt_link']:
        msg += f"🔗 {video['yt_link']}\n"
    msg += "👇 Full instructions below:\n"
    msg += "1️⃣ Play video on YouTube\n2️⃣ Like, Comment, Subscribe\n3️⃣ Screen record full process\n4️⃣ Upload proof below 👇"
    kb = build_task_menu(task['id'], proof_status, verify_status)
    await update.message.reply_photo(
        InputFile(video['thumb']), caption=msg, parse_mode="HTML", reply_markup=kb
    )

# --- Submit Proof Handler ---
async def submit_proof_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    task = get_task_for_user(user.id)
    if not task:
        await update.message.reply_text("❌ No current task.")
        return ConversationHandler.END
    await update.message.reply_text("📤 Send your screen-recording proof (video file):")
    context.user_data['task_id'] = task['id']
    return SUBMIT_PROOF

async def submit_proof_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    task_id = context.user_data.get('task_id')
    if not update.message.video:
        await update.message.reply_text("❗Send a video file as proof.")
        return SUBMIT_PROOF
    file = await update.message.video.get_file()
    file_path = os.path.join(PROOF_PATH, f"{user.id}_{task_id}_{datetime.now().timestamp()}.mp4")
    await file.download_to_drive(file_path)
    submit_proof(task_id, user.id, file_path)
    await update.message.reply_text("✅ Proof uploaded! Waiting for partner's review.")
    return ConversationHandler.END

# --- Approve/Reject Proof (partner) ---
async def proof_review_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split(":")
    task_id, action = int(data[1]), data[2]
    task = get_task_by_id(task_id)
    user = query.from_user
    # Only partner can review
    if user.id not in [task['user_a'], task['user_b']]:
        await query.answer("Not allowed.", show_alert=True)
        return
    # Determine whose proof is being reviewed
    if user.id == task['user_a']:
        reviewee = task['user_b']
        proof_file = task['proof_b']
    else:
        reviewee = task['user_a']
        proof_file = task['proof_a']
    if not proof_file:
        await query.answer("No proof to review.", show_alert=True)
        return
    if action == "approve":
        verify_proof(task_id, user.id, "approved")
        await query.answer("✅ Approved!", show_alert=True)
        await query.edit_message_caption("✅ Proof approved.")
    elif action == "reject":
        verify_proof(task_id, user.id, "rejected")
        await query.answer("❌ Rejected.", show_alert=True)
        await query.edit_message_caption("❌ Proof rejected. Report if cheating.")
    elif action == "report":
        context.user_data['report_task_id'] = task_id
        await query.message.reply_text("🚩 Type reason for reporting:")
        return REPORT_REASON

async def report_reason_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    task_id = context.user_data.get('report_task_id')
    reason = update.message.text.strip()
    task = get_task_by_id(task_id)
    # Assign accused and proof
    if user.id == task['user_a']:
        accused = task['user_b']
        proof_file = task['proof_b']
    else:
        accused = task['user_a']
        proof_file = task['proof_a']
    add_complaint(user.id, accused, task_id, reason, proof_file)
    await update.message.reply_text("🚩 Complaint submitted to admin.")
    return ConversationHandler.END

# --- Admin Panel ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("🚫 Admin only.")
        return
    stats = get_admin_stats()
    await update.message.reply_text(
        f"👮 <b>Admin Panel</b>\n"
        f"Users: {stats['users']}\n"
        f"Active Tasks: {stats['active_tasks']}\n"
        f"Pending Complaints: {stats['complaints']}\n"
        f"Strikes Given: {stats['strikes']}\n"
        f"Banned Users: {stats['banned']}\n",
        parse_mode="HTML", reply_markup=build_admin_menu()
    )

async def admin_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split(":")
    action, target_id = data[1], int(data[2])
    if action == "ban":
        admin_ban_user(target_id)
        await query.answer("User banned.", show_alert=True)
    elif action == "strike":
        admin_strike_user(target_id)
        await query.answer("User struck.", show_alert=True)
    elif action == "unban":
        admin_unban_user(target_id)
        await query.answer("User unbanned.", show_alert=True)
    elif action == "removestrike":
        admin_remove_strike(target_id)
        await query.answer("Strike removed.", show_alert=True)
    await query.edit_message_text("✅ Action complete.")

# --- Main ---
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # --- Clean up job ---
    app.job_queue.run_repeating(timeout_job, interval=180, first=10)

    # --- Handlers ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("menu", main_menu))
    app.add_handler(CommandHandler("pause", pause_user))
    app.add_handler(CommandHandler("resume", resume_user))
    app.add_handler(CommandHandler("status", status_user))
    app.add_handler(CommandHandler("ready", ready_for_task))
    app.add_handler(CommandHandler("mytask", my_task))
    app.add_handler(CommandHandler("myvideos", my_videos))
    app.add_handler(CommandHandler("adminpanel", admin_panel))

    # --- Video Upload Conversation ---
    upload_conv = ConversationHandler(
        entry_points=[CommandHandler("upload", upload_video_start)],
        states={
            UPLOAD_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_title)],
            UPLOAD_THUMB: [MessageHandler(filters.PHOTO, upload_thumb)],
            UPLOAD_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_link)],
            UPLOAD_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_duration)],
        },
        fallbacks=[CommandHandler("cancel", upload_cancel)],
        allow_reentry=True,
    )
    app.add_handler(upload_conv)

    # --- Submit Proof Conversation ---
    proof_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(submit_proof_start, pattern="^submitproof:")],
        states={
            SUBMIT_PROOF: [MessageHandler(filters.VIDEO, submit_proof_receive)],
        },
        fallbacks=[],
        allow_reentry=True,
    )
    app.add_handler(proof_conv)

    # --- Report Complaint Conversation ---
    report_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(proof_review_handler, pattern="^review:")],
        states={
            REPORT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_reason_receive)],
        },
        fallbacks=[],
        allow_reentry=True,
    )
    app.add_handler(report_conv)

    # --- CallbackQuery Handlers ---
    app.add_handler(CallbackQueryHandler(remove_video_handler, pattern="^removevideo:"))
    app.add_handler(CallbackQueryHandler(proof_review_handler, pattern="^review:"))
    app.add_handler(CallbackQueryHandler(admin_action_handler, pattern="^admin:"))

    app.run_polling()

if __name__ == "__main__":
    main()