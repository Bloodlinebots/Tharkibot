import os
import json
import random
import asyncio
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from telegram.error import BadRequest

# ------------------------ Configuration ------------------------

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
VAULT_CHANNEL_ID = -1002572348022
FORCE_JOIN_CHANNEL = "bot_backup" #without @
ADMIN_USER_IDS = [7755789304] #owner

VIDEO_IDS_FILE = "video_ids.json"
USER_SEEN_FILE = "user_seen.json"
SUDO_FILE = "sudo_users.json"
LAST_RESTART_FILE = "restart_time.txt"

last_sent_time = {}

# ------------------------ Helper Functions ------------------------

def load_json(filename, default):
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump(default, f)
    with open(filename, "r") as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

def get_unseen_video(user_id):
    all_ids = load_json(VIDEO_IDS_FILE, [])
    seen_map = load_json(USER_SEEN_FILE, {})
    seen = seen_map.get(str(user_id), [])
    unseen = list(set(all_ids) - set(seen))

    if not all_ids:
        return None

    if not unseen:
        seen_map[str(user_id)] = []
        save_json(USER_SEEN_FILE, seen_map)
        return "RESET"

    return random.choice(unseen)

def mark_seen(user_id, msg_id):
    seen_map = load_json(USER_SEEN_FILE, {})
    seen = seen_map.get(str(user_id), [])
    if msg_id not in seen:
        seen.append(msg_id)
    seen_map[str(user_id)] = seen
    save_json(USER_SEEN_FILE, seen_map)

def get_sudo_users():
    return load_json(SUDO_FILE, [])

def save_sudo_users(users):
    save_json(SUDO_FILE, users)

def is_sudo(user_id: int):
    return user_id in ADMIN_USER_IDS or user_id in get_sudo_users()

# ------------------------ Join Check ------------------------

async def is_user_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(f"@{FORCE_JOIN_CHANNEL}", user_id)
        return member.status in ["member", "administrator", "creator"]
    except BadRequest:
        return False

# ------------------------ Handlers ------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user

    # Notify admin
    admin_id = ADMIN_USER_IDS[0]
    mention = f"@{user.username}" if user.username else user.first_name
    text = f"🚀 User started the bot\nID: <code>{user_id}</code>\nName: {mention}"
    await context.bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")

    if not await is_user_joined(user_id, context):
        join_button = InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")
        reply_markup = InlineKeyboardMarkup([[join_button]])
        await update.message.reply_text("🚫 You must join our channel to use this bot.", reply_markup=reply_markup)
        return

    buttons = [
        [InlineKeyboardButton("DEVELOPER", url="https://t.me/UNBORNVILLIAN")],
        [InlineKeyboardButton("SUPPORT", url="https://t.me/BOTMINE_TECH")]
    ]
    await update.message.reply_photo(
        photo="https://files.catbox.moe/fxsuba.jpg",
        caption="🥵 Welcome to TharkiHub!\n👇 Tap below to explore:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    terms_text = (
        "📜 Read our Terms and Conditions carefully.\n"
        "We do not support or promote any adult content.\n"
        "This bot is only for entertainment and educational purpose.\n"
        "All content is user-submitted, and we hold no responsibility for any misuse."
    )
    terms_button = [
        [InlineKeyboardButton("📘 View Terms", url="https://t.me/bot_backup/7")]
    ]
    await update.message.reply_text(
        text=terms_text,
        reply_markup=InlineKeyboardMarkup(terms_button)
    )

    video_btn = [[InlineKeyboardButton("📥 Get Random Video", callback_data="get_video")]]
    await update.message.reply_text("🔥 Want a random video? Tap below:", reply_markup=InlineKeyboardMarkup(video_btn))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if not await is_user_joined(user_id, context):
        join_button = InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")
        await query.message.reply_text("🚫 You must join our channel to use this bot./n note: if you leave chaneel the  you will be blocked again.",
                                       reply_markup=InlineKeyboardMarkup([[join_button]]))
        return

    now = time.time()
    if user_id in last_sent_time and now - last_sent_time[user_id] < 8:
        await query.message.reply_text("⏳ Please wait 8 seconds before getting another video.")
        return
    last_sent_time[user_id] = now

    msg_id = get_unseen_video(user_id)

    if msg_id == "RESET":
        await query.message.reply_text("✅ You have already watched all videos. Restarting again...")
        msg_id = random.choice(load_json(VIDEO_IDS_FILE, []))

    if msg_id is None:
        await query.message.reply_text("⚠️ No videos available in vault.")
        return

    try:
        await context.bot.copy_message(
            chat_id=query.message.chat_id,
            from_chat_id=VAULT_CHANNEL_ID,
            message_id=msg_id
        )
        mark_seen(user_id, msg_id)
    except BadRequest:
        await query.message.reply_text("⚠️ Error: Video not found or deleted.")
        return

    keyboard = [[InlineKeyboardButton("📥 Get Another Video", callback_data="get_video")]]
    await query.message.reply_text("Want one more? 🙈", reply_markup=InlineKeyboardMarkup(keyboard))

# ------------------------ Main ------------------------

def main():
    if not os.path.exists(LAST_RESTART_FILE):
        with open(LAST_RESTART_FILE, "w") as f:
            f.write(str(int(time.time())))

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler, pattern="get_video"))
    application.run_polling()

if __name__ == "__main__":
    main()
