import os
import asyncio
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.error import BadRequest, TelegramError
from motor.motor_asyncio import AsyncIOMotorClient

# --- CONFIG ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

VAULT_CHANNEL_ID = -1002564608005
LOG_CHANNEL_ID = -1002624785490
ADMIN_USER_ID = 7755789304
DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK = "https://t.me/valahallah"
TERMS_LINK = "https://t.me/bot_backup/7"
WELCOME_IMAGE = "https://graph.org/file/d367814bc3243e72917ab-9f1d63e7b3f46b6716.jpg"

FORCE_JOIN_CHANNELS = [
    {"type": "public", "username": "bot_backup", "name": "RASILI CHU💦"},
    {"type": "private", "chat_id": -1002799718375, "name": "RASMALAI🥵"},
    {"type": "public", "username": "valahallah", "name": "VALAHALLA🔥"},
]

client = AsyncIOMotorClient(MONGO_URI)
db = client["telegram_bot"]

def is_admin(uid): return uid == ADMIN_USER_ID
async def is_sudo(uid): return uid == ADMIN_USER_ID or await db.sudos.find_one({"_id": uid})

def main_keyboard():
    return ReplyKeyboardMarkup([
        ["🎥 Get Random Video"],
        ["ℹ️ Help", "📃 Terms"]
    ], resize_keyboard=True)

async def check_force_join(uid, bot):
    for channel in FORCE_JOIN_CHANNELS:
        try:
            chat_id = f"@{channel['username']}" if channel["type"] == "public" else channel["chat_id"]
            member = await bot.get_chat_member(chat_id, uid)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = update.effective_user

    if await db.banned.find_one({"_id": uid}):
        return await update.message.reply_text("❌ You are banned from using this bot.")

    if not await check_force_join(uid, context.bot):
        buttons = []
        for ch in FORCE_JOIN_CHANNELS:
            url = f"https://t.me/{ch['username']}" if ch["type"] == "public" else (
                await context.bot.create_chat_invite_link(ch["chat_id"])).invite_link
            buttons.append([InlineKeyboardButton(f"🔗 Join {ch['name']}", url=url)])
        buttons.append([InlineKeyboardButton("✅ I’ve Joined", callback_data="force_check")])
        return await update.message.reply_text(
            "*🚫 Access Denied!*\n\n"
            "╭────❰ 𝗙𝗥𝗘𝗘 𝗔𝗖𝗖𝗘𝗦𝗦 ❱─────⎯⎯⎯⎯\n"
            "┊ This bot is *completely FREE* to use 💯\n"
            "┊ Unlimited 🔞 videos without paying a single rupee\n"
            "┊ Just one thing — support us by joining all channels ❤️\n"
            "╰─────────────────────────────\n\n"
            "*👉 Join all channels below to continue:*",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )

    await db.users.update_one({"_id": uid}, {"$set": {"_id": uid}}, upsert=True)
    await context.bot.send_message(LOG_CHANNEL_ID, f"👤 New user: {user.full_name} | ID: {uid}")

    bot_name = (await context.bot.get_me()).first_name
    caption = (
        f"*😈 WELCOME TO {bot_name}!*\\n"
        "Uncover the naughtiest unseen drops 💦 just for you.\\n"
        "👇 Smash the menu button and enjoy!\\n"
        "\\`⚡ Note: This is the official bot of the Vallalah Team.\\`"
    )

    await update.message.reply_photo(
        photo=WELCOME_IMAGE,
        caption=caption,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👨‍💻 Developer", url=DEVELOPER_LINK)],
            [InlineKeyboardButton("👥 Support", url=SUPPORT_LINK), InlineKeyboardButton("📃 Terms", url=TERMS_LINK)],
        ]),
        parse_mode="MarkdownV2"
    )

    await update.message.reply_text("👇 Choose from the menu:", reply_markup=main_keyboard())

async def get_random_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if await db.banned.find_one({"_id": uid}):
        return await update.message.reply_text("❌ You are banned from using this bot.")

    seen_doc = await db.user_videos.find_one({"_id": uid}) or {}
    seen = seen_doc.get("seen", [])

    doc = await db.videos.aggregate([
        {"$match": {"msg_id": {"$nin": seen}}},
        {"$sample": {"size": 1}}
    ]).to_list(1)

    if not doc:
        await db.user_videos.update_one({"_id": uid}, {"$set": {"seen": []}}, upsert=True)
        return await update.message.reply_text("📭 No more unseen videos.\nPlease wait for new uploads!")

    msg_id = doc[0]["msg_id"]

    try:
        await context.bot.copy_message(
            chat_id=uid,
            from_chat_id=VAULT_CHANNEL_ID,
            message_id=msg_id,
            protect_content=True
        )
        await db.user_videos.update_one({"_id": uid}, {"$addToSet": {"seen": msg_id}}, upsert=True)
        await context.bot.send_message(
            chat_id=uid,
            text="✅ Here's your random video.\n👇 Use the menu to get more!",
            reply_markup=main_keyboard()
        )
    except BadRequest as e:
        if "message to copy not found" in str(e):
            await db.videos.delete_one({"msg_id": msg_id})
            await db.user_videos.update_many({}, {"$pull": {"seen": msg_id}})
            await context.bot.send_message(LOG_CHANNEL_ID, f"⚠️ Removed broken video `{msg_id}`", parse_mode="Markdown")
            return await get_random_video(update, context)
        else:
            return await update.message.reply_text(f"⚠️ Error: {e}")
    except TelegramError as e:
        return await update.message.reply_text(f"⚠️ Telegram error: {e}")
    except Exception as e:
        return await update.message.reply_text(f"⚠️ Unknown error: {e}")

async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await is_sudo(uid):
        return

    if update.message.video:
        unique_id = update.message.video.file_unique_id
        exists = await db.videos.find_one({"unique_id": unique_id})
        if exists:
            return await update.message.reply_text("⚠️ Already exists in vault.")
        try:
            sent = await context.bot.forward_message(
                chat_id=VAULT_CHANNEL_ID,
                from_chat_id=uid,
                message_id=update.message.message_id
            )
            await db.videos.insert_one({
                "msg_id": sent.message_id,
                "unique_id": unique_id
            })
            await update.message.reply_text("✅ Forwarded to vault.")
        except Exception as e:
            await update.message.reply_text(f"❌ Upload failed: {e}")
            await context.bot.send_message(LOG_CHANNEL_ID, f"❌ Upload error from {uid}: {e}")

async def force_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    if await check_force_join(uid, context.bot):
        await query.message.delete()
        msg = Update(update.update_id, message=update.effective_message)
        await start(msg, context)
    else:
        await query.edit_message_text("🚫 You haven't joined all required channels.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💬 For help, contact the developer:\n" + DEVELOPER_LINK)

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.forward_message(
            chat_id=update.effective_chat.id,
            from_chat_id="@bot_backup",
            message_id=7,
        )
    except:
        await update.message.reply_text("⚠️ Could not fetch terms. Please check the channel directly.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_sudo(update.effective_user.id):
        return
    total_users = await db.users.count_documents({})
    total_videos = await db.videos.count_documents({})
    total_banned = await db.banned.count_documents({})
    total_sudos = await db.sudos.count_documents({})
    await update.message.reply_text(
        f"📊 *Bot Stats:*\n"
        f"👥 Users: `{total_users}`\n"
        f"🎞 Videos: `{total_videos}`\n"
        f"🚫 Banned: `{total_banned}`\n"
        f"🛡 Sudo Users: `{total_sudos}`",
        parse_mode="Markdown"
    )

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("stats", stats_command))

    app.add_handler(CallbackQueryHandler(force_check_callback, pattern="force_check"))

    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)get random video"), get_random_video))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)help"), help_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)terms"), privacy_command))
    app.add_handler(MessageHandler(filters.VIDEO, auto_upload))

    app.run_polling()

if __name__ == "__main__":
    main()
