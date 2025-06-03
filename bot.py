import os
import json
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.constants import ChatAction
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                          filters, CallbackContext, CallbackQueryHandler, ContextTypes)
from telegram.constants import ChatType
from telegram.helpers import mention_html

# Constants
ADMIN_USER_ID = 7755789304
VAULT_CHANNEL_ID = -1002624785490
FORCE_JOIN_CHANNEL = "bot_backup"
DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK = "https://t.me/botmine_tech"
TERMS_LINK = "https://t.me/bot_backup/7"

# File paths
VIDEO_FILE = "video_ids.json"
USER_FILE = "user_seen.json"
SUDO_FILE = "sudos.json"
BAN_FILE = "banned_users.json"

# Load or initialize data files
def load_json(filename, default):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    return default

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

video_ids = load_json(VIDEO_FILE, [])
user_seen = load_json(USER_FILE, {})
sudo_users = load_json(SUDO_FILE, [])
banned_users = load_json(BAN_FILE, [])

# Helper functions
def is_admin(user_id):
    return user_id == ADMIN_USER_ID

def is_sudo(user_id):
    return user_id in sudo_users or is_admin(user_id)

# Commands
async def add_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /addsudo <user_id>")
        return
    try:
        sudo_id = int(context.args[0])
        if sudo_id not in sudo_users:
            sudo_users.append(sudo_id)
            save_json(SUDO_FILE, sudo_users)
            await update.message.reply_text(f"✅ User `{sudo_id}` added as sudo.", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ User is already a sudo.")
    except:
        await update.message.reply_text("❌ Invalid user ID.")

async def remove_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /removesudo <user_id>")
        return
    try:
        sudo_id = int(context.args[0])
        if sudo_id in sudo_users:
            sudo_users.remove(sudo_id)
            save_json(SUDO_FILE, sudo_users)
            await update.message.reply_text(f"✅ User `{sudo_id}` removed from sudo.", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ User is not a sudo.")
    except:
        await update.message.reply_text("❌ Invalid user ID.")

async def sudo_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not sudo_users:
        await update.message.reply_text("No sudo users found.")
        return
    text = "**👑 Sudo Users:**\n" + "\n".join([f"- `{uid}`" for uid in sudo_users])
    await update.message.reply_text(text, parse_mode="Markdown")

# Sample uploader for sudo/admin
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_sudo(user_id):
        return
    if update.message.video:
        message = await context.bot.copy_message(
            chat_id=VAULT_CHANNEL_ID,
            from_chat_id=update.message.chat_id,
            message_id=update.message.message_id
        )
        video_ids.append(message.message_id)
        save_json(VIDEO_FILE, video_ids)
        await update.message.reply_text("✅ Video uploaded to vault.")

# Basic /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("👤 Support", url=SUPPORT_LINK)],
        [InlineKeyboardButton("📘 View Terms", url=TERMS_LINK)]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    text = f"👋 Hello {user.mention_html()}\nYour ID: <code>{user.id}</code>"
    await update.message.reply_html(text, reply_markup=markup)

# Main
def main():
    app = ApplicationBuilder().token(os.environ["BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addsudo", add_sudo))
    app.add_handler(CommandHandler("removesudo", remove_sudo))
    app.add_handler(CommandHandler("sudolist", sudo_list))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    print("Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
    
