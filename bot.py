import os
import json
import random
import asyncio
import threading
import zipfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,  # ✅ FIXED
    ContextTypes,
    filters,         # ✅ FIXED
)

# Configurations
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
VAULT_CHANNEL_ID = -1002624785490
FORCE_JOIN_CHANNEL = "bot_backup"
ADMIN_USER_ID = 7755789304
TERMS_LINK = "https://t.me/bot_backup/7"
DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK = "https://t.me/botmine_tech"
WELCOME_IMAGE = "https://files.catbox.moe/19j4mc.jpg"

VIDEO_FILE = "video_ids.json"
USER_FILE = "user_seen.json"
SUDO_FILE = "sudos.json"
BANNED_FILE = "banned.json"

cooldown_time = 8
cooldowns = {}

# Helper functions
def load_json(filename, default):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    else:
        return default

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

videos = load_json(VIDEO_FILE, [])
user_seen = load_json(USER_FILE, {})
sudo_users = load_json(SUDO_FILE, [])
banned_users = load_json(BANNED_FILE, [])

def is_admin(user_id):
    return user_id == ADMIN_USER_ID

def is_sudo(user_id):
    return user_id in sudo_users or is_admin(user_id)

def is_banned(user_id):
    return user_id in banned_users

def delete_after_delay(bot, chat_id, message_id, delay):
    import time
    time.sleep(delay)
    try:
        asyncio.run(bot.delete_message(chat_id=chat_id, message_id=message_id))
    except Exception:
        pass

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if is_banned(user_id):
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return

    try:
        member = await context.bot.get_chat_member(f"@{FORCE_JOIN_CHANNEL}", user_id)
        if member.status in ["left", "kicked"]:
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")]]
            )
            await update.message.reply_text(
                "🚫 You must join our channel to use this bot.\n\n"
                "⚠️ If you leave the channel, you will be restricted from using the bot.\n\n"
                "✅ After joining, please use /start again.",
                reply_markup=keyboard,
            )
            return
    except Exception:
        pass

    user = update.effective_user
    log_text = (
        f"📥 New User Started Bot\n\n"
        f"👤 Name: {user.full_name}\n"
        f"🆔 ID: {user.id}\n"
        f"📛 Username: @{user.username if user.username else 'N/A'}"
    )
    await context.bot.send_message(chat_id=VAULT_CHANNEL_ID, text=log_text)

    bot_name = (await context.bot.get_me()).first_name
    caption = (
        f"🥵 Welcome to {bot_name}!\n"
        "Here you will access the most unseen videos.\n👇 Tap below to explore:"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📩 Get Random Video", callback_data="get_video")],
            [InlineKeyboardButton("Developer", url=DEVELOPER_LINK)],
            [
                InlineKeyboardButton("Support", url=SUPPORT_LINK),
                InlineKeyboardButton("Help", callback_data="show_help"),
            ],
        ]
    )

    await update.message.reply_photo(
        photo=WELCOME_IMAGE,
        caption=caption,
        reply_markup=keyboard,
    )

    disclaimer = (
        "⚠️ **Disclaimer** ⚠️\n\n"
        "We do NOT produce or spread adult content.\n"
        "This bot is only for file forwarding.\n"
        "If the file content contains adult videos, the bot holds no responsibility.\n"
        "Please read terms and conditions carefully."
    )
    buttons = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📘 Terms & Conditions", url=TERMS_LINK)]]
    )
    await context.bot.send_message(
        chat_id=user_id,
        text=disclaimer,
        reply_markup=buttons,
        parse_mode="Markdown",
    )

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = (await context.bot.get_me()).first_name
    caption = (
        f"🥵 Welcome to {bot_name}!\n"
        "Here you will access the most unseen videos.\n👇 Tap below to explore:"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📩 Get Random Video", callback_data="get_video")],
            [InlineKeyboardButton("Developer", url=DEVELOPER_LINK)],
            [
                InlineKeyboardButton("Support", url=SUPPORT_LINK),
                InlineKeyboardButton("Help", callback_data="show_help"),
            ],
        ]
    )
    await query.edit_message_media(
        media=InputMediaPhoto(WELCOME_IMAGE, caption=caption),
        reply_markup=keyboard,
    )

async def callback_get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if is_banned(user_id):
        await query.message.reply_text("🚫 You are banned from using this bot.")
        return

    now = asyncio.get_event_loop().time()
    if not is_admin(user_id):
        if user_id in cooldowns and cooldowns[user_id] > now:
            wait = int(cooldowns[user_id] - now)
            await query.message.reply_text(f"⏳ Please wait {wait} seconds before getting another video.")
            return
        cooldowns[user_id] = now + cooldown_time

    seen = user_seen.get(str(user_id), [])
    unseen = list(set(videos) - set(seen))

    if not unseen:
        await query.message.reply_text(
            "✅ You have watched all videos of our server 😅\nRestarting the list for you!"
        )
        user_seen[str(user_id)] = []
        save_json(USER_FILE, user_seen)
        unseen = videos.copy()

    random.shuffle(unseen)

    for msg_id in unseen:
        try:
            sent = await context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=VAULT_CHANNEL_ID,
                message_id=msg_id,
                protect_content=True,
            )
            threading.Thread(
                target=delete_after_delay,
                args=(context.bot, user_id, sent.message_id, 10800),
                daemon=True,
            ).start()

            seen.append(msg_id)
            user_seen[str(user_id)] = seen
            save_json(USER_FILE, user_seen)

            await query.message.reply_text(
                "Want another? 😈",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("📥 Get Another Video", callback_data="get_video")]]
                ),
            )
            return
        except Exception:
            if msg_id in videos:
                videos.remove(msg_id)
                save_json(VIDEO_FILE, videos)

    await query.message.reply_text("⚠️ No videos available right now, please try later.")

async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_sudo(user_id):
        return

    if update.message.video:
        try:
            sent = await context.bot.copy_message(
                chat_id=VAULT_CHANNEL_ID,
                from_chat_id=update.message.chat_id,
                message_id=update.message.message_id,
            )
            videos.append(sent.message_id)
            save_json(VIDEO_FILE, videos)
            await update.message.reply_text("✅ Video uploaded and saved to vault.")
        except Exception:
            await update.message.reply_text("⚠️ Failed to upload.")

async def show_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Use /privacy to see the bot's Terms and Conditions")

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.forward_message(
            chat_id=update.effective_chat.id, from_chat_id="@bot_backup", message_id=7
        )
    except Exception:
        await update.message.reply_text("⚠️ Failed to fetch privacy message.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("If you need any help then contact developer")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ Unknown command.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(callback_get_video, pattern="^get_video$"))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern="^back$"))
    app.add_handler(CallbackQueryHandler(show_help_callback, pattern="^show_help$"))

    app.add_handler(MessageHandler(filters.VIDEO, auto_upload))  # ✅ Video upload for sudo users

    app.add_handler(MessageHandler(filters.COMMAND, unknown))  # Unknown commands

    app.run_polling()

if __name__ == "__main__":
    main()
