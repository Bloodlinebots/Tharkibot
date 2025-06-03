import os
import random
import threading
import asyncio
import zipfile
import time
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# --------- CONFIG ------------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGODB_URI")

if not TOKEN or not MONGO_URI:
    raise EnvironmentError("❌ Missing TELEGRAM_BOT_TOKEN or MONGODB_URI in environment variables.")

client = MongoClient(MONGO_URI)
db = client["telegram_bot"]
videos_col = db["videos"]
user_seen_col = db["user_seen"]
sudo_col = db["sudo_users"]
banned_col = db["banned_users"]

VAULT_CHANNEL_ID = -1002624785490
FORCE_JOIN_CHANNEL = "bot_backup"
ADMIN_USER_ID = 7755789304
DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK = "https://t.me/botmine_tech"
TERMS_LINK = "https://t.me/bot_backup/7"
WELCOME_IMAGE = "https://files.catbox.moe/19j4mc.jpg"

COOLDOWN = 8
cooldowns = {}

# --------- DB HELPERS ------------
def get_videos():
    return [v["id"] for v in videos_col.find()]

def add_video(msg_id):
    videos_col.update_one({"id": msg_id}, {"$set": {"id": msg_id}}, upsert=True)

def remove_video(msg_id):
    videos_col.delete_one({"id": msg_id})

def get_user_seen(uid):
    data = user_seen_col.find_one({"_id": str(uid)})
    return data["seen"] if data and "seen" in data else []

def set_user_seen(uid, seen):
    user_seen_col.update_one({"_id": str(uid)}, {"$set": {"seen": seen}}, upsert=True)

def get_flag(uid):
    data = user_seen_col.find_one({"_id": str(uid)})
    return data.get("msg_flag", False) if data else False

def set_flag(uid, value):
    user_seen_col.update_one({"_id": str(uid)}, {"$set": {"msg_flag": value}}, upsert=True)

def get_all_users():
    return [doc["_id"] for doc in user_seen_col.find({"seen": {"$exists": True}})]

def get_sudo_users():
    return [doc["_id"] for doc in sudo_col.find()]

def add_sudo_user(uid):
    sudo_col.update_one({"_id": uid}, {"$set": {"_id": uid}}, upsert=True)

def remove_sudo_user(uid):
    sudo_col.delete_one({"_id": uid})

def get_banned_users():
    return [doc["_id"] for doc in banned_col.find()]

def is_banned(uid):
    return banned_col.find_one({"_id": uid}) is not None

# --------- LOGIC HELPERS -----------
def is_admin(uid):
    return uid == ADMIN_USER_ID

def is_sudo(uid):
    return uid in get_sudo_users() or is_admin(uid)

def delete_after_delay(bot, chat_id, message_id, delay, loop):
    time.sleep(delay)
    try:
        asyncio.run_coroutine_threadsafe(
            bot.delete_message(chat_id=chat_id, message_id=message_id),
            loop
        )
    except Exception:
        pass

# --------- HANDLERS -----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if is_banned(uid):
        await update.message.reply_text("🛘 You are banned from using this bot.")
        return

    try:
        member = await context.bot.get_chat_member(f"@{FORCE_JOIN_CHANNEL}", uid)
        if member.status in ["left", "kicked"]:
            btn = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")]]
            )
            await update.message.reply_text(
                "🛘 You must join our channel to use this bot.\n\n⚠️ If you leave, you will be restricted.\n\n✅ After joining, use /start",
                reply_markup=btn,
            )
            return
    except Exception:
        pass

    user = update.effective_user
    log_text = (
        f"📥 New User Started Bot\n\n"
        f"👤 Name: {user.full_name}\n"
        f"🆗 ID: {user.id}\n"
        f"📛 Username: @{user.username if user.username else 'N/A'}"
    )
    await context.bot.send_message(chat_id=VAULT_CHANNEL_ID, text=log_text)

    bot_name = (await context.bot.get_me()).first_name
    caption = (
        f"🥵 Welcome to {bot_name}!\n"
        "Here you will access the most unseen videos.\n👇 Tap below to explore:"
    )

    await update.message.reply_photo(
        photo=WELCOME_IMAGE,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📩 Get Random Video", callback_data="get_video")],
                [InlineKeyboardButton("Developer", url=DEVELOPER_LINK)],
                [
                    InlineKeyboardButton("Support", url=SUPPORT_LINK),
                    InlineKeyboardButton("Help", callback_data="show_privacy_info"),
                ],
            ]
        ),
    )

    disclaimer_text = (
        "⚠️ **Disclaimer** ⚠️\n\n"
        "We do NOT produce or spread adult content.\n"
        "This bot is only for forwarding files.\n"
        "If videos are adult, we take no responsibility.\n"
        "Please read terms and conditions."
    )
    buttons = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📘 Terms & Conditions", url=TERMS_LINK)]]
    )

    await context.bot.send_message(
        chat_id=uid, text=disclaimer_text, reply_markup=buttons, parse_mode="Markdown"
    )

async def callback_get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    if is_banned(uid):
        await query.message.reply_text("🛘 You are banned from using this bot.")
        return

    now = asyncio.get_event_loop().time()
    if not is_admin(uid):
        if uid in cooldowns and cooldowns[uid] > now:
            wait = int(cooldowns[uid] - now)
            await query.message.reply_text(f"⏳ Please wait {wait} seconds before getting another video.")
            return
        cooldowns[uid] = now + COOLDOWN

    seen = get_user_seen(uid)
    all_videos = get_videos()
    unseen = list(set(all_videos) - set(seen))

    if not unseen:
        if not get_flag(uid):
            await query.message.reply_text("✅ You have watched all videos on our server 😅\nRestarting the list for you!")
            set_flag(uid, True)
        set_user_seen(uid, [])
        unseen = all_videos.copy()

    random.shuffle(unseen)

    for msg_id in unseen:
        try:
            sent = await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=VAULT_CHANNEL_ID,
                message_id=msg_id,
                protect_content=True,
            )
            threading.Thread(
                target=delete_after_delay,
                args=(context.bot, uid, sent.message_id, 10800, context.application.loop),
                daemon=True,
            ).start()

            seen.append(msg_id)
            set_user_seen(uid, seen)
            set_flag(uid, False)

            await query.message.reply_text(
                f"🎬 Video {len(seen)}/{len(all_videos)} watched.\nWant another? 😈",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("📥 Get Another Video", callback_data="get_video")]]
                ),
            )
            return
        except Exception:
            remove_video(msg_id)

    await query.message.reply_text("⚠️ No videos available right now, please try later.")

async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        return

    if update.message.video:
        try:
            sent = await context.bot.copy_message(
                chat_id=VAULT_CHANNEL_ID,
                from_chat_id=update.message.chat.id,
                message_id=update.message.message_id,
            )
            add_video(sent.message_id)
            await update.message.reply_text("✅ Video uploaded and saved to vault.")
        except Exception:
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
    except Exception:
        await update.message.reply_text("⚠️ Failed to fetch privacy message.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("If you need any help, contact the developer.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("🛘 You are not authorized.")
        return

    text = update.message.text.partition(" ")[2]
    if not text:
        await update.message.reply_text("Usage: /broadcast Your message here")
        return

    count = 0
    for user_id in get_all_users():
        try:
            await context.bot.send_message(chat_id=int(user_id), text=text)
            count += 1
        except Exception:
            pass

    await update.message.reply_text(f"📣 Broadcast sent to {count} users.")

async def add_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("🛘 Only owner can add sudo.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /addsudo <user_id>")
        return

    try:
        new_sudo = int(context.args[0])
        if new_sudo not in get_sudo_users():
            add_sudo_user(new_sudo)
            await update.message.reply_text(f"✅ Added {new_sudo} as sudo.")
        else:
            await update.message.reply_text("User already a sudo.")
    except ValueError:
        await update.message.reply_text("Invalid user ID.")

async def remove_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("🛘 Only owner can remove sudo.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /remsudo <user_id>")
        return

    try:
        rem_sudo = int(context.args[0])
        if rem_sudo in get_sudo_users():
            remove_sudo_user(rem_sudo)
            await update.message.reply_text(f"✅ Removed {rem_sudo} from sudo.")
        else:
            await update.message.reply_text("User is not a sudo.")
    except ValueError:
        await update.message.reply_text("Invalid user ID.")

async def run_bot():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("addsudo", add_sudo))
    app.add_handler(CommandHandler("remsudo", remove_sudo))
    app.add_handler(CallbackQueryHandler(callback_get_video, pattern="get_video"))
    app.add_handler(CallbackQueryHandler(show_privacy_info, pattern="show_privacy_info"))
    app.add_handler(MessageHandler(filters.VIDEO, auto_upload))

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(run_bot())
