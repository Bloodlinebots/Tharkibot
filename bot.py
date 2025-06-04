import os
import random
import threading
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from motor.motor_asyncio import AsyncIOMotorClient

# --------- CONFIG ------------

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI") or "mongodb://localhost:27017"
client = AsyncIOMotorClient(MONGO_URI)
db = client["telegram_bot"]

VAULT_CHANNEL_ID = -1002624785490
FORCE_JOIN_CHANNEL = "bot_backup"
ADMIN_USER_ID = 7755789304
DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK = "https://t.me/botmine_tech"
TERMS_LINK = "https://t.me/bot_backup/7"
WELCOME_IMAGE = "https://files.catbox.moe/19j4mc.jpg"

COOLDOWN = 8
cooldowns = {}

# --------- HELPERS ------------

def is_admin(uid):
    return uid == ADMIN_USER_ID

def is_sudo(uid, sudo_list):
    return uid in sudo_list or is_admin(uid)

async def get_user_data(uid):
    user = await db.users.find_one({"_id": uid})
    return user or {"_id": uid, "seen": [], "msg_sent": False}

async def save_user_data(data):
    await db.users.replace_one({"_id": data["_id"]}, data, upsert=True)

async def get_all_videos():
    videos = await db.videos.find().to_list(None)
    return [v["msg_id"] for v in videos]

async def add_video(msg_id):
    await db.videos.update_one({"msg_id": msg_id}, {"$set": {"msg_id": msg_id}}, upsert=True)

async def delete_after_delay(bot, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

# --------- HANDLERS -----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    banned = await db.banned.find_one({"_id": uid})
    if banned:
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return

    try:
        member = await context.bot.get_chat_member(f"@{FORCE_JOIN_CHANNEL}", uid)
        if member.status in ["left", "kicked"]:
            btn = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")]]
            )
            await update.message.reply_text(
                "🚫 You must join our channel to use this bot.\n\n"
                "⚠️ If you leave, you will be restricted.\n\n"
                "✅ After joining, use /start",
                reply_markup=btn,
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

async def callback_get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    banned = await db.banned.find_one({"_id": uid})
    if banned:
        await query.message.reply_text("🚫 You are banned from using this bot.")
        return

    now = asyncio.get_event_loop().time()
    if not is_admin(uid):
        if uid in cooldowns and cooldowns[uid] > now:
            wait = int(cooldowns[uid] - now)
            await query.message.reply_text(f"⏳ Please wait {wait} seconds before getting another video.")
            return
        cooldowns[uid] = now + COOLDOWN

    user_data = await get_user_data(uid)
    videos = await get_all_videos()
    seen = user_data.get("seen", [])
    unseen = list(set(videos) - set(seen))

    if not unseen:
        if not user_data.get("msg_sent", False):
            await query.message.reply_text("✅ You have watched all videos on our server 😅\nRestarting the list for you!")
            user_data["msg_sent"] = True
        user_data["seen"] = []
        await save_user_data(user_data)
        unseen = videos.copy()

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
                target=asyncio.run,
                args=(delete_after_delay(context.bot, uid, sent.message_id, 10800),),
                daemon=True,
            ).start()

            user_data["seen"].append(msg_id)
            user_data["msg_sent"] = False
            await save_user_data(user_data)

            total_videos = len(videos)
            watched = len(user_data["seen"])
            await query.message.reply_text(
                f"🎬 Video {watched}/{total_videos} watched.\nWant another? 😈",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("📥 Get Another Video", callback_data="get_video")]]
                ),
            )
            return
        except Exception:
            await db.videos.delete_one({"msg_id": msg_id})

    await query.message.reply_text("⚠️ No videos available right now, please try later.")

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

# --------- ADMIN COMMANDS -----------

async def add_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return
    try:
        target_id = int(context.args[0])
        await db.sudos.update_one({"_id": target_id}, {"$set": {"_id": target_id}}, upsert=True)
        await update.message.reply_text(f"✅ Added {target_id} as sudo user.")
    except:
        await update.message.reply_text("⚠️ Usage: /addsudo 123456789")

async def remove_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return
    try:
        target_id = int(context.args[0])
        await db.sudos.delete_one({"_id": target_id})
        await update.message.reply_text(f"❌ Removed {target_id} from sudo users.")
    except:
        await update.message.reply_text("⚠️ Usage: /remsudo 123456789")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sudo_list = [s["_id"] async for s in db.sudos.find()]
    uid = update.effective_user.id
    if not is_sudo(uid, sudo_list):
        return
    try:
        target_id = int(context.args[0])
        await db.banned.update_one({"_id": target_id}, {"$set": {"_id": target_id}}, upsert=True)
        await update.message.reply_text(f"🚫 User {target_id} banned.")
    except:
        await update.message.reply_text("⚠️ Usage: /ban 123456789")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sudo_list = [s["_id"] async for s in db.sudos.find()]
    uid = update.effective_user.id
    if not is_sudo(uid, sudo_list):
        return
    try:
        target_id = int(context.args[0])
        await db.banned.delete_one({"_id": target_id})
        await update.message.reply_text(f"✅ User {target_id} unbanned.")
    except:
        await update.message.reply_text("⚠️ Usage: /unban 123456789")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sudo_list = [s["_id"] async for s in db.sudos.find()]
    uid = update.effective_user.id
    if not is_sudo(uid, sudo_list):
        return

    if not context.args:
        await update.message.reply_text("⚠️ Usage: /broadcast your message here")
        return

    msg = " ".join(context.args)
    users = db.users.find()
    count = 0

    async for user in users:
        try:
            await context.bot.send_message(chat_id=user["_id"], text=msg)
            count += 1
        except:
            pass
    await update.message.reply_text(f"✅ Broadcast sent to {count} users.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sudo_list = [s["_id"] async for s in db.sudos.find()]
    uid = update.effective_user.id
    if not is_sudo(uid, sudo_list):
        return

    total_users = await db.users.count_documents({})
    total_videos = await db.videos.count_documents({})
    total_banned = await db.banned.count_documents({})
    total_sudos = await db.sudos.count_documents({})

    text = (
        "📊 **Bot Statistics**\n\n"
        f"👥 Total Users: `{total_users}`\n"
        f"🎞 Total Videos: `{total_videos}`\n"
        f"🚫 Banned Users: `{total_banned}`\n"
        f"🛡 Sudo Users: `{total_sudos}`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# --------- MAIN -----------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_get_video, pattern="get_video"))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern="back_to_start"))
    app.add_handler(CallbackQueryHandler(show_privacy_info, pattern="show_privacy_info"))
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
