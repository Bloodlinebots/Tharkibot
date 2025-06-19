import os
import asyncio
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from telegram.error import BadRequest, TelegramError
from motor.motor_asyncio import AsyncIOMotorClient

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI") or "mongodb://localhost:27017"

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
VIDEO_LOCK_TTL = 10

def is_admin(uid): return uid == ADMIN_USER_ID
def is_sudo(uid, sudo_list): return uid in sudo_list or is_admin(uid)

async def add_video(msg_id):
    await db.videos.update_one({"msg_id": msg_id}, {"$set": {"msg_id": msg_id}}, upsert=True)

async def delete_after_delay(bot, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except:
        pass

async def get_and_lock_video(uid):
    await db.videos.update_many(
        {
            "locked": True,
            "lock_time": {"$lt": datetime.datetime.utcnow() - datetime.timedelta(seconds=VIDEO_LOCK_TTL)}
        },
        {"$set": {"locked": False, "lock_time": None}}
    )

    watched_doc = await db.watched.find_one({"_id": uid}) or {}
    watched_ids = watched_doc.get("watched_ids", [])

    return await db.videos.find_one_and_update(
        {
            "msg_id": {"$nin": watched_ids},
            "locked": {"$ne": True}
        },
        {"$set": {"locked": True, "lock_time": datetime.datetime.utcnow()}},
        sort=[("$natural", 1)]
    )

async def callback_get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    if await db.banned.find_one({"_id": uid}):
        await query.message.reply_text("🚫 You are banned from using this bot.")
        return

    now = asyncio.get_event_loop().time()
    if not is_admin(uid):
        if uid in cooldowns and cooldowns[uid] > now:
            wait = int(cooldowns[uid] - now)
            await query.message.reply_text(f"⏳ Please wait {wait} seconds before getting another video.")
            return
        cooldowns[uid] = now + COOLDOWN

    for _ in range(5):
        video = await get_and_lock_video(uid)
        if not video:
            await db.watched.update_one({"_id": uid}, {"$set": {"watched_ids": []}}, upsert=True)
            continue

        msg_id = video["msg_id"]

        try:
            sent = await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=VAULT_CHANNEL_ID,
                message_id=msg_id,
                protect_content=True,
            )
            await db.videos.update_one({"msg_id": msg_id}, {"$set": {"locked": False, "lock_time": None}})
            await db.watched.update_one({"_id": uid}, {"$addToSet": {"watched_ids": msg_id}}, upsert=True)
            context.application.create_task(delete_after_delay(context.bot, uid, sent.message_id, 10800))

            await query.message.reply_text(
                "😈 Want another?",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("📥 Get Another Video", callback_data="get_video")]]
                )
            )
            return

        except BadRequest as e:
            await db.videos.update_one({"msg_id": msg_id}, {"$set": {"locked": False, "lock_time": None}})
            if "MESSAGE_ID_INVALID" in str(e):
                await db.videos.delete_one({"msg_id": msg_id})
                await context.bot.send_message(LOG_CHANNEL_ID, f"❌ Corrupt video deleted: `{msg_id}`", parse_mode="Markdown")
            else:
                await query.message.reply_text(f"⚠️ Telegram error: {e}")
        except Exception as e:
            await query.message.reply_text(f"⚠️ Unexpected error: {e}")
            await db.videos.update_one({"msg_id": msg_id}, {"$set": {"locked": False, "lock_time": None}})

async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    sudo_list = [s["_id"] async for s in db.sudos.find()]
    if not is_sudo(uid, sudo_list): return

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

    user = update.effective_user
    log_text = (
        f"📥 New User Started Bot\n\n"
        f"👤 Name: {user.full_name}\n"
        f"🆔 ID: {user.id}\n"
        f"📛 Username: @{user.username or 'N/A'}"
    )
    await context.bot.send_message(LOG_CHANNEL_ID, log_text)

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
        ])
    )

    disclaimer = (
        "⚠️ **Disclaimer** ⚠️\n\n"
        "We do NOT produce or spread adult content.\n"
        "This bot is only for forwarding files.\n"
        "Please read terms and conditions."
    )
    btn = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📘 Terms & Conditions", url=TERMS_LINK)]]
    )
    await context.bot.send_message(uid, disclaimer, reply_markup=btn, parse_mode="Markdown")

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

# Admin commands
async def add_sudo(update, context): ...
async def remove_sudo(update, context): ...
async def ban_user(update, context): ...
async def unban_user(update, context): ...
async def stats_command(update, context): ...

# Main
async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(callback_get_video, pattern="get_video"))
    app.add_handler(CallbackQueryHandler(show_privacy_info, pattern="show_privacy_info"))
    app.add_handler(MessageHandler(filters.VIDEO, auto_upload))
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
