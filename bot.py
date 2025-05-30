import os
import json
import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes
)
from telegram.error import BadRequest

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
VAULT_CHANNEL_ID = -1002572348022  # Your private channel ID
FORCE_JOIN_CHANNEL = "sjsjsskrj"   # Channel username (no @)
ADMIN_USER_ID =   7755789304       # Your Telegram user ID

VIDEO_IDS_FILE = "video_ids.json"
USER_SEEN_FILE = "user_seen.json"

# ---------- JSON Helper ----------
def load_json(filename, default):
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump(default, f)
    with open(filename, "r") as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

# ---------- Video Logic ----------
def get_unseen_video(user_id):
    all_ids = load_json(VIDEO_IDS_FILE, [])
    seen_map = load_json(USER_SEEN_FILE, {})
    seen = seen_map.get(str(user_id), [])
    unseen = list(set(all_ids) - set(seen))

    if not all_ids:
        return None  # No videos at all

    if not unseen:
        return None  # All videos seen

    return random.choice(unseen)

def mark_seen(user_id, msg_id):
    seen_map = load_json(USER_SEEN_FILE, {})
    seen = seen_map.get(str(user_id), [])
    if msg_id not in seen:
        seen.append(msg_id)
    seen_map[str(user_id)] = seen
    save_json(USER_SEEN_FILE, seen_map)

# ---------- Force Join Check ----------
async def is_user_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(f"@{FORCE_JOIN_CHANNEL}", user_id)
        return member.status in ["member", "administrator", "creator"]
    except BadRequest:
        return False

# ---------- /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_joined(user_id, context):
        join_button = InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")
        markup = InlineKeyboardMarkup([[join_button]])
        await update.message.reply_text("🚫 You must join our channel to use this bot.", reply_markup=markup)
        return

    buttons = [
        [InlineKeyboardButton("your_button_name 1", url="https://t.me/unbornvillian")],
        [InlineKeyboardButton("your_button_name 2", url="https://t.me/unbornvillian")]
    ]
    await update.message.reply_photo(
        photo="https://files.catbox.moe/fxsuba.jpg",
        caption="🥵 Welcome to TharkiHub!\n👇 Tap below to explore:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    video_btn = [[InlineKeyboardButton("📥 Get Random MMS Video", callback_data="get_video")]]
    await update.message.reply_text("🔥 Want a random MMS? Tap below:", reply_markup=InlineKeyboardMarkup(video_btn))

# ---------- Video Button ----------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if not await is_user_joined(user_id, context):
        join_button = InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")
        await query.message.reply_text("🚫 You must join our channel to use this bot.",
                                       reply_markup=InlineKeyboardMarkup([[join_button]]))
        return

    msg_id = get_unseen_video(user_id)
    if not msg_id:
        await query.message.reply_text("✅ You have watched all videos! Please check back later.")
        return

    try:
        await context.bot.forward_message(
            chat_id=query.message.chat_id,
            from_chat_id=VAULT_CHANNEL_ID,
            message_id=msg_id
        )
        mark_seen(user_id, msg_id)
        keyboard = [[InlineKeyboardButton("📥 Get Another MMS Video", callback_data="get_video")]]
        await query.message.reply_text("Want one more? 😈", reply_markup=InlineKeyboardMarkup(keyboard))
    except BadRequest:
        await query.message.reply_text("⚠️ Error: Video not found or deleted.")

# ---------- Admin: /add_video ----------
async def add_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a video message to add it.")
        return

    msg_id = update.message.reply_to_message.message_id
    print("Storing message ID:", msg_id)  # Debug print

    video_ids = load_json(VIDEO_IDS_FILE, [])
    if msg_id not in video_ids:
        video_ids.append(msg_id)
        save_json(VIDEO_IDS_FILE, video_ids)

        # ✅ Try forwarding the video now to confirm it's accessible
        try:
            await context.bot.forward_message(
                chat_id=update.effective_chat.id,
                from_chat_id=VAULT_CHANNEL_ID,
                message_id=msg_id
            )
            await update.message.reply_text("✅ Video added and verified successfully.")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Video saved but could not be accessed: {e}")
    else:
        await update.message.reply_text("⚠️ This video is already in the list.")

# ---------- Admin: /delete_video ----------
async def delete_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a video message to delete it.")
        return

    msg_id = update.message.reply_to_message.message_id
    video_ids = load_json(VIDEO_IDS_FILE, [])
    if msg_id in video_ids:
        video_ids.remove(msg_id)
        save_json(VIDEO_IDS_FILE, video_ids)

        seen_map = load_json(USER_SEEN_FILE, {})
        for user in seen_map:
            seen_map[user] = [vid for vid in seen_map[user] if vid != msg_id]
        save_json(USER_SEEN_FILE, seen_map)

        await update.message.reply_text("✅ Video removed successfully.")
    else:
        await update.message.reply_text("⚠️ This video was not found in the list.")

# ---------- Main ----------
def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler, pattern="get_video"))
    application.add_handler(CommandHandler("add_video", add_video))
    application.add_handler(CommandHandler("delete_video", delete_video))
    application.run_polling()

if __name__ == "__main__":
    main()
