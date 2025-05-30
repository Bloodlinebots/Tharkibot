import os
import json
import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import BadRequest

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
VAULT_CHANNEL_ID = -1002572348022  # Replace with your private channel ID
FORCE_JOIN_CHANNEL = "sjsjsskrj"   # Replace with your channel username (without @)
ADMIN_ID = 7755789304  # 🔐 Replace with your own Telegram ID (integer)

VIDEO_IDS_FILE = "video_ids.json"
USER_HISTORY_FILE = "user_history.json"

def load_video_ids():
    if not os.path.exists(VIDEO_IDS_FILE):
        return []
    with open(VIDEO_IDS_FILE, "r") as f:
        data = json.load(f)
        return data.get("video_ids", [])

def save_video_id(new_id):
    ids = load_video_ids()
    if new_id not in ids:
        ids.append(new_id)
        with open(VIDEO_IDS_FILE, "w") as f:
            json.dump({"video_ids": ids}, f)
        return True
    return False

def load_user_history():
    if not os.path.exists(USER_HISTORY_FILE):
        return {}
    with open(USER_HISTORY_FILE, "r") as f:
        return json.load(f)

def save_user_history(history):
    with open(USER_HISTORY_FILE, "w") as f:
        json.dump(history, f)

def get_next_video_for_user(user_id):
    video_ids = load_video_ids()
    history = load_user_history()

    watched = set(history.get(str(user_id), []))
    remaining = [vid for vid in video_ids if vid not in watched]

    if not remaining:
        history[str(user_id)] = []
        save_user_history(history)
        remaining = video_ids.copy()

    next_id = random.choice(remaining)
    history.setdefault(str(user_id), []).append(next_id)
    save_user_history(history)
    return next_id

async def is_user_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=f"@{FORCE_JOIN_CHANNEL}", user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except BadRequest:
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_joined(user_id, context):
        join_button = InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")
        reply_markup = InlineKeyboardMarkup([[join_button]])
        await update.message.reply_text("🚫 You must join our channel to use this bot.", reply_markup=reply_markup)
        return

    # Welcome image with buttons
    welcome_buttons = [
        [InlineKeyboardButton("your_button_name 1", url="https://t.me/your_username")],
        [InlineKeyboardButton("your_button_name 2", url="https://t.me/your_username")]
    ]
    welcome_markup = InlineKeyboardMarkup(welcome_buttons)
    await update.message.reply_photo(
        photo="https://files.catbox.moe/fxsuba.jpg",
        caption="🥵 Welcome to TharkiHub!\n👇 Tap below to explore:",
        reply_markup=welcome_markup
    )

    # Video button
    video_button = [[InlineKeyboardButton("📥 Get Random MMS Video", callback_data="get_video")]]
    await update.message.reply_text("🔥 Want a random MMS? Tap below:", reply_markup=InlineKeyboardMarkup(video_button))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not await is_user_joined(user_id, context):
        join_button = InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")
        reply_markup = InlineKeyboardMarkup([[join_button]])
        await query.message.reply_text("🚫 You must join our channel to use this bot.", reply_markup=reply_markup)
        await query.answer()
        return

    await query.answer()
    msg_id = get_next_video_for_user(user_id)
    await context.bot.forward_message(
        chat_id=query.message.chat_id,
        from_chat_id=VAULT_CHANNEL_ID,
        message_id=msg_id
    )
    keyboard = [[InlineKeyboardButton("📥 Get Another MMS Video", callback_data="get_video")]]
    await query.message.reply_text("Want one more? 😈", reply_markup=InlineKeyboardMarkup(keyboard))

async def add_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 You're not authorized to add videos.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /addvideo <message_id>")
        return

    try:
        msg_id = int(context.args[0])
        added = save_video_id(msg_id)
        if added:
            await update.message.reply_text(f"✅ Message ID {msg_id} added to the list.")
        else:
            await update.message.reply_text(f"⚠️ Message ID {msg_id} already exists.")
    except ValueError:
        await update.message.reply_text("❌ Invalid message ID. Use numbers only.")

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("addvideo", add_video))
    application.add_handler(CallbackQueryHandler(button_handler, pattern="get_video"))
    application.run_polling()

if __name__ == "__main__":
    main()
