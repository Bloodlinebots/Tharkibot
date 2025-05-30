import os
import json
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters
)

# ---------------- CONFIG ----------------
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

# ---------------- HELPERS ----------------
def load_json(file, default):
    if os.path.exists(file):
        with open(file, 'r') as f:
            return json.load(f)
    return default

def save_json(file, data):
    with open(file, 'w') as f:
        json.dump(data, f, indent=2)

videos = load_json(VIDEO_FILE, [])
user_seen = load_json(USER_FILE, {})
sudo_users = load_json(SUDO_FILE, [])
banned_users = load_json(BANNED_FILE, [])

# ---------------- DECORATORS ----------------
def is_admin(uid):
    return uid == ADMIN_USER_ID

def is_sudo(uid):
    return uid in sudo_users or is_admin(uid)

def is_banned(uid):
    return uid in banned_users

# ---------------- HANDLERS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_banned(uid):
        return

    try:
        member = await context.bot.get_chat_member(f"@{FORCE_JOIN_CHANNEL}", uid)
        if member.status in ["left", "kicked"]:
            btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")]
            ])
            await update.message.reply_text(
                "🚫 You must join our channel to use this bot.\n\n"
                "⚠️ Note: If you leave the channel, you will be restricted from using the bot.\n\n"
                "✅ After joining, please use /start",
                reply_markup=btn
            )
            return
    except:
        return

    await update.message.reply_photo(
        photo=WELCOME_IMAGE,
        caption="🥵 Welcome to TharkiHub!\n👇 Tap below to explore:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Get Random Video", callback_data="get_video")],
            [InlineKeyboardButton("📘 View Terms", url=TERMS_LINK)],
            [InlineKeyboardButton("Developer", url=DEVELOPER_LINK)],
            [InlineKeyboardButton("Support", url=SUPPORT_LINK)]
        ])
    )

async def callback_get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    if is_banned(uid):
        return

    now = asyncio.get_event_loop().time()
    if not is_admin(uid):
        if uid in cooldowns and cooldowns[uid] > now:
            wait = int(cooldowns[uid] - now)
            await query.message.reply_text(f"⏳ Please wait {wait} seconds before getting another video.")
            return
        cooldowns[uid] = now + cooldown_time

    seen = user_seen.get(str(uid), [])
    unseen = list(set(videos) - set(seen))

    if not unseen:
        await query.message.reply_text("✅ You have watched all videos of our server 😅")
        user_seen[str(uid)] = []
        save_json(USER_FILE, user_seen)
        return

    msg_id = random.choice(unseen)
    try:
        await context.bot.copy_message(
            chat_id=uid,
            from_chat_id=VAULT_CHANNEL_ID,
            message_id=msg_id
        )
        seen.append(msg_id)
        user_seen[str(uid)] = seen
        save_json(USER_FILE, user_seen)

        await query.message.reply_text(
            "Want another? 😈",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 Get Another Video", callback_data="get_video")]
            ])
        )
    except:
        await query.message.reply_text("⚠️ Video not found or deleted.")

async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        return

    if update.message.video:
        try:
            sent = await context.bot.copy_message(
                chat_id=VAULT_CHANNEL_ID,
                from_chat_id=update.message.chat_id,
                message_id=update.message.message_id
            )
            videos.append(sent.message_id)
            save_json(VIDEO_FILE, videos)
            await update.message.reply_text("✅ Video uploaded and saved to vault.")
        except:
            await update.message.reply_text("⚠️ Failed to upload.")

# ---------------- MAIN ----------------
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(callback_get_video, pattern="get_video"))
app.add_handler(MessageHandler(filters.VIDEO, auto_upload))

print("✅ Bot is running...")
app.run_polling()
