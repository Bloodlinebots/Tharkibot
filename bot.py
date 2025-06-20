import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from telegram.error import BadRequest, TelegramError
from motor.motor_asyncio import AsyncIOMotorClient

# ----- CONFIG -----
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

VAULT_CHANNEL_ID = -1002564608005
LOG_CHANNEL_ID = -1002624785490
FORCE_JOIN_CHANNELS = [
    {"type": "public", "username": "bot_backup"},
    {"type": "private", "invite_link": "https://t.me/+5TtbYhth9Q1hOWI1", "name": "rasmalai"}
]
ADMIN_USER_ID = 7755789304
DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK = "https://t.me/botmine_tech"
TERMS_LINK = "https://t.me/bot_backup/7"
WELCOME_IMAGE = "https://graph.org/file/a13e9733afdad69720d67.jpg"

# ----- INIT -----
client = AsyncIOMotorClient(MONGO_URI)
db = client["telegram_bot"]

# ----- HELPERS -----
def is_admin(uid): return uid == ADMIN_USER_ID
async def is_sudo(uid):
    sudo_list = [s["_id"] async for s in db.sudos.find()]
    return uid in sudo_list or is_admin(uid)

async def add_video(msg_id, unique_id=None):
    data = {"msg_id": msg_id}
    if unique_id:
        data["unique_id"] = unique_id
    await db.videos.update_one({"msg_id": msg_id}, {"$set": data}, upsert=True)

async def delete_after_delay(bot, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except:
        pass

async def check_force_join(uid, bot):
    join_buttons = []
    for channel in FORCE_JOIN_CHANNELS:
        try:
            if channel["type"] == "public":
                member = await bot.get_chat_member(f"@{channel['username']}", uid)
                if member.status in ["left", "kicked"]:
                    join_buttons.append(
                        InlineKeyboardButton(f"Join @{channel['username']}", url=f"https://t.me/{channel['username']}")
                    )
            elif channel["type"] == "private":
                join_buttons.append(
                    InlineKeyboardButton(f"Join {channel.get('name', 'Private Channel')}", url=channel["invite_link"])
                )
        except:
            if channel["type"] == "public":
                join_buttons.append(
                    InlineKeyboardButton(f"Join @{channel['username']}", url=f"https://t.me/{channel['username']}")
                )
    return join_buttons

# ----- HANDLERS -----

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if await db.banned.find_one({"_id": uid}):
        return await update.message.reply_text("🛑 You are banned from using this bot.")

    join_buttons = await check_force_join(uid, context.bot)
    if join_buttons:
        join_buttons.append(InlineKeyboardButton("✅ I Joined", callback_data="recheck_join"))
        return await update.message.reply_text(
            "🛑 You must join the following channels to use this bot:",
            reply_markup=InlineKeyboardMarkup([[btn] for btn in join_buttons])
        )

    await db.users.update_one({"_id": uid}, {"$set": {"_id": uid}}, upsert=True)

    user = update.effective_user
    log_text = (
        f"📥 New User Started Bot\n"
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
            [InlineKeyboardButton("Developer", url=DEVELOPER_LINK)],
            [
                InlineKeyboardButton("Support", url=SUPPORT_LINK),
                InlineKeyboardButton("Help", callback_data="show_privacy_info")
            ]
        ])
    )

    disclaimer = (
        "⚠️ **Disclaimer** ⚠️\n\n"
        "We do NOT produce or spread adult content.\n"
        "This bot is only for forwarding files.\n"
        "Please read terms and conditions."
    )
    await context.bot.send_message(
        uid, disclaimer,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📘 Terms & Conditions", url=TERMS_LINK)]]),
        parse_mode="Markdown"
    )

async def callback_get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    if await db.banned.find_one({"_id": uid}):
        return await query.message.reply_text("🛑 You are banned from using this bot.")

    user_videos_doc = await db.user_videos.find_one({"_id": uid})
    seen = user_videos_doc.get("seen", []) if user_videos_doc else []

    video_docs = await db.videos.aggregate([
        {"$match": {"msg_id": {"$nin": seen}}},
        {"$sample": {"size": 4}}
    ]).to_list(4)

    if not video_docs:
        return await query.message.reply_text("📭 No more unseen videos. Please wait for more uploads.")

    for video in video_docs:
        msg_id = video["msg_id"]
        try:
            sent = await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=VAULT_CHANNEL_ID,
                message_id=msg_id,
                protect_content=True,
            )
            await db.user_videos.update_one(
                {"_id": uid},
                {"$addToSet": {"seen": msg_id}},
                upsert=True
            )
            context.application.create_task(delete_after_delay(context.bot, uid, sent.message_id, 3600))
        except BadRequest as e:
            if "MESSAGE_ID_INVALID" in str(e):
                await db.videos.delete_one({"msg_id": msg_id})
                await db.user_videos.update_many({}, {"$pull": {"seen": msg_id}})
                await context.bot.send_message(LOG_CHANNEL_ID, f"⚠️ Removed broken video `{msg_id}`", parse_mode="Markdown")
                return await callback_get_video(update, context)
            else:
                await query.message.reply_text(f"⚠️ Error: {e}")
                return
        except TelegramError as e:
            await query.message.reply_text(f"⚠️ Telegram error: {e}")
            return
        except Exception as e:
            await query.message.reply_text(f"⚠️ Unknown error: {e}")
            return

    await context.bot.send_message(
        chat_id=uid,
        text="""This video will auto-destruct in 1 hour ⌛
We auto-delete it to keep things clean & copyright-safe 🚫""",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Get More Random Videos", callback_data="get_video")]
        ])
    )

async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await is_sudo(uid):
        return

    if update.message.video:
        video = update.message.video
        unique_id = video.file_unique_id

        existing = await db.videos.find_one({"unique_id": unique_id})
        if existing:
            return await update.message.reply_text("⚠️ This video already exists in the vault.")

        try:
            sent = await context.bot.copy_message(
                chat_id=VAULT_CHANNEL_ID,
                from_chat_id=update.message.chat_id,
                message_id=update.message.message_id,
            )
            try:
                await add_video(sent.message_id, unique_id=unique_id)
                await update.message.reply_text("✅ Uploaded to vault and saved.")
            except Exception as e:
                await update.message.reply_text(f"⚠️ Video copied but DB failed: {e}")
                await context.bot.send_message(LOG_CHANNEL_ID, f"❌ DB error by {uid}: {e}")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Upload failed: {e}")
            await context.bot.send_message(LOG_CHANNEL_ID, f"❌ Upload error by {uid}: {e}")

async def show_privacy_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("/privacy - View bot's Terms and Conditions")

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.forward_message(
            chat_id=update.effective_chat.id,
            from_chat_id="@bot_backup",
            message_id=7,
        )
    except:
        await update.message.reply_text("⚠️ Could not fetch privacy policy.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Need help? Contact the developer.")

# ----- ADMIN -----
async def add_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return
    try:
        target = int(context.args[0])
        await db.sudos.update_one({"_id": target}, {"$set": {"_id": target}}, upsert=True)
        await update.message.reply_text(f"✅ Added {target} as sudo.")
    except:
        await update.message.reply_text("⚠️ Usage: /addsudo user_id")

async def remove_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return
    try:
        target = int(context.args[0])
        await db.sudos.delete_one({"_id": target})
        await update.message.reply_text(f"❌ Removed {target} from sudo.")
    except:
        await update.message.reply_text("⚠️ Usage: /remsudo user_id")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_sudo(update.effective_user.id):
        return
    try:
        target = int(context.args[0])
        await db.banned.update_one({"_id": target}, {"$set": {"_id": target}}, upsert=True)
        await update.message.reply_text(f"🚫 Banned user {target}")
    except:
        await update.message.reply_text("⚠️ Usage: /ban user_id")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_sudo(update.effective_user.id):
        return
    try:
        target = int(context.args[0])
        await db.banned.delete_one({"_id": target})
        await update.message.reply_text(f"✅ Unbanned user {target}")
    except:
        await update.message.reply_text("⚠️ Usage: /unban user_id")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_sudo(update.effective_user.id):
        return
    if not context.args:
        return await update.message.reply_text("⚠️ Usage: /broadcast your message")

    msg = " ".join(context.args)
    count = 0
    async for user in db.users.find():
        try:
            await context.bot.send_message(user["_id"], msg)
            count += 1
        except:
            pass
    await update.message.reply_text(f"✅ Broadcast sent to {count} users.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_sudo(update.effective_user.id):
        return
    v = await db.videos.count_documents({})
    u = await db.users.count_documents({})
    s = await db.sudos.count_documents({})
    b = await db.banned.count_documents({})
    await update.message.reply_text(
        f"📊 **Bot Stats**\n\n🎞 Videos: `{v}`\n👥 Users: `{u}`\n🛡 Sudo: `{s}`\n🚫 Banned: `{b}`",
        parse_mode="Markdown"
    )

# ----- MAIN -----
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_get_video, pattern="get_video"))
    app.add_handler(CallbackQueryHandler(show_privacy_info, pattern="show_privacy_info"))
    app.add_handler(CallbackQueryHandler(start, pattern="recheck_join"))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(CommandHandler("addsudo", add_sudo))
    app.add_handler(CommandHandler("remsudo", remove_sudo))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler(["stats", "status"], stats_command))

    app.add_handler(MessageHandler(filters.VIDEO, auto_upload))
    app.run_polling()

if __name__ == "__main__":
    main()
