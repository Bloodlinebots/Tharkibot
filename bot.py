import os
import json
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ---------------- CONFIG ----------------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
VAULT_CHANNEL_ID = -1002624785490
FORCE_JOIN_CHANNEL = "bot_backup"
ADMIN_USER_ID = 7755789304
TERMS_LINK = "https://t.me/bot_backup/7"
DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK = "https://t.me/botmine_tech"

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

# ---------------- COMMANDS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_banned(uid): return

    try:
        member = await context.bot.get_chat_member(f"@{FORCE_JOIN_CHANNEL}", uid)
        if member.status in ["left", "kicked"]:
            btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")]
            ])
            await update.message.reply_text(
                "🚫 You must join our channel to use this bot.\n\n"
                "⚠️ Note: If you leave the channel, you will be restricted from using the bot.\n"
                "✅ After joining, please use /start",
                reply_markup=btn
            )
            return
    except:
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Developer", url=DEVELOPER_LINK)],
        [InlineKeyboardButton("Support", url=SUPPORT_LINK)]
    ])
    await update.message.reply_text(
        "🥵 Welcome to TharkiHub!\n👇 Tap below to explore:",
        reply_markup=keyboard
    )

    disclaimer = (
        "⚠️ Disclaimer:\n"
        "We do not support or promote any adult content.\n"
        "This bot contains 18+ content. Use at your own discretion."
    )
    terms_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 View Terms", url=TERMS_LINK)]
    ])
    await update.message.reply_text(disclaimer, reply_markup=terms_btn)

async def get_random_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_banned(uid): return
    if not videos:
        await update.message.reply_text("⚠️ No videos available in vault.")
        return

    if not is_admin(uid):
        now = asyncio.get_event_loop().time()
        if uid in cooldowns and cooldowns[uid] > now:
            wait = int(cooldowns[uid] - now)
            await update.message.reply_text(f"⏳ Please wait {wait} seconds before getting another video.")
            return
        cooldowns[uid] = now + cooldown_time

    seen = user_seen.get(str(uid), [])
    unseen = list(set(videos) - set(seen))

    if not unseen:
        await update.message.reply_text("✅ You have watched all videos of our server 😅")
        user_seen[str(uid)] = []
        save_json(USER_FILE, user_seen)
        return

    msg_id = random.choice(unseen)
    try:
        await context.bot.forward_message(uid, VAULT_CHANNEL_ID, msg_id)
        seen.append(msg_id)
        user_seen[str(uid)] = seen
        save_json(USER_FILE, user_seen)
    except:
        await update.message.reply_text("⚠️ Video not found or deleted.")

async def add_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid): return

    if update.message.reply_to_message:
        try:
            msg_id = update.message.reply_to_message.message_id
            if msg_id not in videos:
                videos.append(msg_id)
                save_json(VIDEO_FILE, videos)
                await update.message.reply_text("✅ Video added successfully.")
            else:
                await update.message.reply_text("⚠️ Video is already in list.")
        except:
            await update.message.reply_text("⚠️ Failed to add video.")

async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid): return

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

async def delete_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    videos.clear()
    save_json(VIDEO_FILE, videos)
    save_json(USER_FILE, {})
    await update.message.reply_text("🧹 All videos and seen data deleted.")

async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_sudo(update.effective_user.id): return
    await update.message.reply_text(
        f"📊 Stats:\n"
        f"Total videos: {len(videos)}\n"
        f"Total users: {len(user_seen)}\n"
        f"Banned: {len(banned_users)}\n"
        f"Sudos: {len(sudo_users)}"
    )

# ---------------- MAIN ----------------
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("get", get_random_video))
app.add_handler(CommandHandler("add_video", add_video))
app.add_handler(CommandHandler("delete_all", delete_all))
app.add_handler(CommandHandler("stat", stat))
app.add_handler(MessageHandler(filters.VIDEO, auto_upload))

print("✅ Bot is running...")
app.run_polling()
