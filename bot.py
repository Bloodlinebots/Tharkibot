import os
import asyncio
import datetime
import redis
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import BadRequest
from motor.motor_asyncio import AsyncIOMotorClient
from redlock import Redlock

# ---------- CONFIG ----------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

client = AsyncIOMotorClient(MONGO_URI)
db = client["telegram_bot"]

VAULT_CHANNEL_ID = -1002564608005
LOG_CHANNEL_ID = -1002624785490
FORCE_JOIN_CHANNEL = "bot_backup"
ADMIN_USER_ID = 7755789304
DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK = "https://t.me/botmine_tech"
TERMS_LINK = "https://t.me/bot_backup/7"
WELCOME_IMAGE = "https://files.catbox.moe/19j4mc.jpg"

COOLDOWN = 5
cooldowns = {}

# Redis client + Redlock
redis_client = redis.Redis(host="localhost", port=6379, db=0)
redlock = Redlock([{"host": "localhost", "port": 6379, "db": 0}])

# ---------- HELPERS ----------
def is_admin(uid):
    return uid == ADMIN_USER_ID

def is_sudo(uid, sudo_list):
    return uid in sudo_list or is_admin(uid)

async def add_video(msg_id):
    await db.videos.update_one({"msg_id": msg_id}, {"$set": {"msg_id": msg_id}}, upsert=True)

async def delete_after_delay(bot, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except:
        pass

# ---------- REDLOCK VIDEO FETCH ----------
async def get_video_with_redlock(uid):
    watched_doc = await db.watched.find_one({"_id": uid}) or {}
    watched_ids = watched_doc.get("watched_ids", [])

    for _ in range(5):
        lock = redlock.lock("video_lock", 1000)
        if lock:
            video = await db.videos.find_one({"msg_id": {"$nin": watched_ids}})
            if video:
                msg_id = video["msg_id"]
                await db.watched.update_one(
                    {"_id": uid}, {"$addToSet": {"watched_ids": msg_id}}, upsert=True
                )
                redlock.unlock(lock)
                return video
            redlock.unlock(lock)
        await asyncio.sleep(0.2)
    return None

# ---------- HANDLERS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if await db.banned.find_one({"_id": uid}):
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return

    try:
        member = await context.bot.get_chat_member(f"@{FORCE_JOIN_CHANNEL}", uid)
        if member.status in ["left", "kicked"]:
            btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")]
            ])
            await update.message.reply_text(
                "🚫 You must join our channel to use this bot.\n\n✅ After joining, use /start",
                reply_markup=btn,
            )
            return
    except:
        pass

    await db.users.update_one({"_id": uid}, {"$set": {"_id": uid}}, upsert=True)

    bot_name = (await context.bot.get_me()).first_name
    caption = (
        f"🥵 Welcome to {bot_name}!\n"
        "Here you will access the most unseen videos.\n👇 Tap below to explore:"
    )

    await update.message.reply_photo(
        photo=WELCOME_IMAGE,
        caption=caption,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Get Random Video", callback_data="get_video")],
            [InlineKeyboardButton("👨‍💻 Developer", url=DEVELOPER_LINK)],
            [
                InlineKeyboardButton("🛠 Support", url=SUPPORT_LINK),
                InlineKeyboardButton("📘 Help", callback_data="show_privacy_info"),
            ],
        ]),
    )

    disclaimer = (
        "⚠️ **Disclaimer** ⚠️\n\n"
        "We do NOT produce or spread adult content.\n"
        "This bot is only for forwarding files.\n"
        "Please read terms and conditions."
    )
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 Terms & Conditions", url=TERMS_LINK)]
    ])
    await context.bot.send_message(uid, disclaimer, reply_markup=btn, parse_mode="Markdown")

async def callback_get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    if await db.banned.find_one({"_id": uid}):
        await query.message.reply_text("🚫 You are banned from using this bot.")
        return

    now = asyncio.get_event_loop().time()
    if uid in cooldowns and cooldowns[uid] > now:
        wait = int(cooldowns[uid] - now)
        await query.message.reply_text(f"⏳ Please wait {wait} seconds before getting another video.")
        return
    cooldowns[uid] = now + COOLDOWN

    video = await get_video_with_redlock(uid)
    if not video:
        await db.watched.update_one({"_id": uid}, {"$set": {"watched_ids": []}}, upsert=True)
        await query.message.reply_text("📭 No more videos! Resetting watch history... Try again.")
        return

    msg_id = video["msg_id"]
    try:
        sent = await context.bot.copy_message(
            chat_id=uid,
            from_chat_id=VAULT_CHANNEL_ID,
            message_id=msg_id,
            protect_content=True,
        )
        context.application.create_task(delete_after_delay(context.bot, uid, sent.message_id, 10800))

        await query.message.reply_text(
            "😈 Want another?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 Get Another Video", callback_data="get_video")]
            ]),
        )
    except BadRequest:
        await db.videos.delete_one({"msg_id": msg_id})
        await context.bot.send_message(LOG_CHANNEL_ID, f"❌ Corrupt video deleted: `{msg_id}`", parse_mode="Markdown")
        await query.message.reply_text("⚠️ That video was broken. Trying another...")
        await asyncio.sleep(1)
        await callback_get_video(update, context)

async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    sudo_list = [s["_id"] async for s in db.sudos.find()]
    if not is_sudo(uid, sudo_list):
        return

    if update.message.video:
        try:
            sent = await context.bot.copy_message(
                chat_id=VAULT_CHANNEL_ID,
                from_chat_id=update.message.chat_id,
                message_id=update.message.message_id,
            )
            await add_video(sent.message_id)
            await update.message.reply_text("✅ Video uploaded and saved to vault.")
        except:
            await update.message.reply_text("⚠️ Failed to upload.")

async def show_privacy_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("/privacy - Use this to see bot's Terms and Conditions")

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.forward_message(
            chat_id=update.effective_chat.id,
            from_chat_id="@bot_backup",
            message_id=7,
        )
    except:
        await update.message.reply_text("⚠️ Failed to fetch privacy message.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ If you need any help, contact the developer.")

# ---------- MAIN ----------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(callback_get_video, pattern="get_video"))
    app.add_handler(CallbackQueryHandler(show_privacy_info, pattern="show_privacy_info"))
    app.add_handler(MessageHandler(filters.VIDEO, auto_upload))

    app.run_polling()

if __name__ == "__main__":
    main()
