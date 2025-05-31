import os
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters
)
from pymongo import MongoClient

# ---------------- CONFIG ----------------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")  # MongoDB URI environment variable

VAULT_CHANNEL_ID = -1002624785490
FORCE_JOIN_CHANNEL = "bot_backup"
ADMIN_USER_ID = 7755789304
TERMS_LINK = "https://t.me/bot_backup/7"
DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK = "https://t.me/botmine_tech"
WELCOME_IMAGE = "https://files.catbox.moe/19j4mc.jpg"

cooldown_time = 8
cooldowns = {}

# ---------------- MONGO DB SETUP ----------------
client = MongoClient(MONGO_URI)
db = client["bot_database"]

videos_col = db["videos"]
user_seen_col = db["user_seen"]
sudo_col = db["sudos"]
banned_col = db["banned"]

# ---------------- STORAGE HELPERS ----------------

def load_videos():
    return [doc["message_id"] for doc in videos_col.find({})]

def save_video(msg_id):
    if not videos_col.find_one({"message_id": msg_id}):
        videos_col.insert_one({"message_id": msg_id})

def remove_video(msg_id):
    videos_col.delete_one({"message_id": msg_id})

def load_user_seen():
    data = {}
    for doc in user_seen_col.find({}):
        data[doc["user_id"]] = doc.get("seen_videos", [])
    return data

def save_user_seen(user_id, seen_list):
    user_seen_col.update_one(
        {"user_id": user_id},
        {"$set": {"seen_videos": seen_list}},
        upsert=True
    )

def load_sudos():
    return [doc["user_id"] for doc in sudo_col.find({})]

def add_sudo(user_id):
    sudo_col.update_one(
        {"user_id": user_id},
        {"$set": {}},
        upsert=True
    )

def load_banned():
    return [doc["user_id"] for doc in banned_col.find({})]

def add_banned(user_id):
    banned_col.update_one(
        {"user_id": user_id},
        {"$set": {}},
        upsert=True
    )

def remove_banned(user_id):
    banned_col.delete_one({"user_id": user_id})

# ---------------- LOAD DATA ON STARTUP ----------------
videos = load_videos()
user_seen = load_user_seen()
sudo_users = load_sudos()
banned_users = load_banned()

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
        await update.message.reply_text("🚫 You are banned from using this bot.")
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

    await update.message.reply_photo(
        photo=WELCOME_IMAGE,
        caption=caption,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Get Random Video", callback_data="get_video")],
            [InlineKeyboardButton("Developer", url=DEVELOPER_LINK)],
            [InlineKeyboardButton("Support", url=SUPPORT_LINK)]
        ])
    )

    disclaimer_text = (
        "⚠️ **Disclaimer** ⚠️\n\n"
        "We do NOT produce or spread adult content.\n"
        "This bot is only for file forwarding.\n"
        "If the file content contains adult videos, the bot holds no responsibility.\n"
        "Please read terms and conditions carefully."
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 Terms & Conditions", url=TERMS_LINK)]
    ])

    await context.bot.send_message(
        chat_id=uid,
        text=disclaimer_text,
        reply_markup=buttons,
        parse_mode='Markdown'
    )


async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = (await context.bot.get_me()).first_name
    caption = (
        f"🥵 Welcome to {bot_name}!\n"
        "Here you will access the most unseen videos.\n👇 Tap below to explore:"
    )
    await query.edit_message_media(
        media=InputMediaPhoto(WELCOME_IMAGE, caption=caption),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Get Random Video", callback_data="get_video")],
            [InlineKeyboardButton("Developer", url=DEVELOPER_LINK)],
            [InlineKeyboardButton("Support", url=SUPPORT_LINK)]
        ])
    )

async def callback_get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    if is_banned(uid):
        await query.message.reply_text("🚫 You are banned from using this bot.")
        return

    now = asyncio.get_event_loop().time()
    if not is_admin(uid):
        if uid in cooldowns and cooldowns[uid] > now:
            wait = int(cooldowns[uid] - now)
            await query.message.reply_text(f"⏳ Please wait {wait} seconds before getting another video.")
            return
        cooldowns[uid] = now + cooldown_time

    seen = user_seen.get(uid, [])
    unseen = list(set(videos) - set(seen))

    if not unseen:
        await query.message.reply_text("✅ You have watched all videos of our server 😅\nRestarting the list for you!")
        user_seen[uid] = []
        save_user_seen(uid, [])
        unseen = videos.copy()

    random.shuffle(unseen)

    for msg_id in unseen:
        try:
            await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=VAULT_CHANNEL_ID,
                message_id=msg_id
            )
            seen.append(msg_id)
            user_seen[uid] = seen
            save_user_seen(uid, seen)

            await query.message.reply_text(
                "Want another? 😈",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📥 Get Another Video", callback_data="get_video")]
                ])
            )
            return
        except Exception:
            if msg_id in videos:
                videos.remove(msg_id)
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
                from_chat_id=update.message.chat_id,
                message_id=update.message.message_id
            )
            videos.append(sent.message_id)
            save_video(sent.message_id)
            await update.message.reply_text("✅ Video uploaded and saved to vault.")
        except Exception:
            await update.message.reply_text("⚠️ Failed to upload.")

# ------------- ADMIN COMMANDS --------------

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("🚫 You are not authorized to use this command.")
        return

    text = update.message.text.partition(' ')[2]
    if not text:
        await update.message.reply_text("Usage: /broadcast Your message here")
        return

    count = 0
    for user_id in user_seen.keys():
        try:
            await context.bot.send_message(chat_id=int(user_id), text=text)
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"📣 Broadcast sent to {count} users.")

async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("🚫 You are not authorized to use this command.")
        return

    # As now files are stored in MongoDB, you might want to implement DB backup separately.
    await update.message.reply_text("⚠️ Backup command not supported with MongoDB storage.")

async def delete_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("🚫 You are not authorized to use this command.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /deletevideo message_id")
        return

    try:
        msg_id = int(args[0])
        if msg_id in videos:
            videos.remove(msg_id)
            remove_video(msg_id)
            await update.message.reply_text(f"✅ Video {msg_id} deleted from vault.")
        else:
            await update.message.reply_text("❌ Video ID not found.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")

async def add_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("🚫 Only admin can add sudo users.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /addsudo user_id")
        return

    try:
        new_sudo = int(args[0])
        if new_sudo not in sudo_users:
            sudo_users.append(new_sudo)
            add_sudo(new_sudo)
            await update.message.reply_text(f"✅ User {new_sudo} added as sudo.")
        else:
            await update.message.reply_text("User already sudo.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("🚫 You are not authorized to ban users.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /ban user_id")
        return

    try:
        user_to_ban = int(args[0])
        if user_to_ban not in banned_users:
            banned_users.append(user_to_ban)
            add_banned(user_to_ban)
            await update.message.reply_text(f"🚫 User {user_to_ban} banned.")
        else:
            await update.message.reply_text("User already banned.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("🚫 You are not authorized to unban users.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /unban user_id")
        return

    try:
        user_to_unban = int(args[0])
        if user_to_unban in banned_users:
            banned_users.remove(user_to_unban)
            remove_banned(user_to_unban)
            await update.message.reply_text(f"✅ User {user_to_unban} unbanned.")
        else:
            await update.message.reply_text("User not banned.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("🚫 You are not authorized to view stats.")
        return

    total_videos = len(videos)
    total_users = len(user_seen)
    total_sudos = len(sudo_users)
    total_banned = len(banned_users)

    text = (
        f"📊 Bot Statistics:\n"
        f"Total Videos: {total_videos}\n"
        f"Total Users: {total_users}\n"
        f"Sudo Users: {total_sudos}\n"
        f"Banned Users: {total_banned}"
    )
    await update.message.reply_text(text)

# ---------------- MAIN ----------------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_get_video, pattern="get_video"))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern="back_to_start"))
    app.add_handler(MessageHandler(filters.VIDEO & filters.User(user_id=sudo_users), auto_upload))

    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("backup", backup))
    app.add_handler(CommandHandler("deletevideo", delete_video))
    app.add_handler(CommandHandler("addsudo", add_sudo))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("stats", stats))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
