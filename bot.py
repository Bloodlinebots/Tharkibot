 os
import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from telegram.error import TelegramError
from motor.motor_asyncio import AsyncIOMotorClient

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIG ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
VAULT_CHANNEL_ID = -1002564608005
LOG_CHANNEL_ID = -1002624785490
ADMIN_USER_ID = 7755789304
DEFAULT_POINTS = 20
REFERRAL_REWARD = 25

FORCE_JOIN_CHANNELS = [
    {"type": "public", "username": "bot_backup", "name": "RASILI CHU💦"},
    {"type": "private", "chat_id": -1002799718375, "name": "RASMALAI🥵"}
]

DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK = "https://t.me/your_support_channel"
WELCOME_IMAGE = "https://graph.org/file/a13e9733afdad69720d67.jpg"

# --- DB Setup ---
client = AsyncIOMotorClient(MONGO_URI)
db = client["telegram_bot"]

# --- Utilities ---
def is_admin(uid): return uid == ADMIN_USER_ID

def main_keyboard():
    return ReplyKeyboardMarkup([
        ["🏙 VIDEO", "📷 PHOTO"],
        ["💰 POINTS", "💸 BUY"],
        ["🔗 /refer"]
    ], resize_keyboard=True)

async def check_force_join(uid, bot):
    for channel in FORCE_JOIN_CHANNELS:
        try:
            chat_id = f"@{channel['username']}" if channel["type"] == "public" else channel["chat_id"]
            member = await bot.get_chat_member(chat_id, uid)
            if member.status in ["left", "kicked"]:
                return False
        except Exception as e:
            logger.warning(f"[ForceJoin] Error: {e}")
            return False
    return True

# --- /start command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = update.effective_user

    if await db.banned.find_one({"_id": uid}):
        return await update.message.reply_text("❌ You are banned from using this bot.")

    if not await check_force_join(uid, context.bot):
        buttons = []
        for ch in FORCE_JOIN_CHANNELS:
            if ch["type"] == "public":
                buttons.append([InlineKeyboardButton(f"🔗 Join {ch['name']}", url=f"https://t.me/{ch['username']}")])
            else:
                invite = await context.bot.create_chat_invite_link(ch["chat_id"])
                buttons.append([InlineKeyboardButton(f"🔗 Join {ch['name']}", url=invite.invite_link)])
        buttons.append([InlineKeyboardButton("✅ Subscribed", callback_data="check_joined")])
        return await update.message.reply_text(
            "🚫 You must join our channels to use this bot.\n\n✅ After joining, press 'Subscribed'",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    referred_by = None
    if context.args and context.args[0].isdigit():
        referred_by = int(context.args[0])
        if referred_by == uid:
            referred_by = None

    user_doc = await db.users.find_one({"_id": uid})
    if not user_doc:
        await db.users.insert_one({"_id": uid, "points": DEFAULT_POINTS})
        if referred_by:
            await db.referrals.insert_one({"_id": uid, "by": referred_by})
            await db.users.update_one({"_id": referred_by}, {"$inc": {"points": REFERRAL_REWARD}})
            try:
                await context.bot.send_message(referred_by, f"🎉 You earned {REFERRAL_REWARD} coins for referring!")
            except Exception as e:
                logger.warning(f"Referral notify failed: {e}")
    else:
        if "points" not in user_doc:
            await db.users.update_one({"_id": uid}, {"$set": {"points": DEFAULT_POINTS}})

    bot_info = await context.bot.get_me()
    caption = (
        f"👋 **Welcome to {bot_info.first_name}**\n\n"
        "🚀 This bot gives you access to high-quality media!\n\n"
        "🎯 Features:\n"
        "▪️ Random Photos/Videos\n▪️ Earn Coins via Referrals\n▪️ Buy Premium Access\n\n"
        f"👥 Referral Bonus: {REFERRAL_REWARD} coins\n"
        f"🪙 You start with {DEFAULT_POINTS} Free coins!\n\n"
        f"🔗 Refer link (https://t.me/{bot_info.username}?start={uid})"
    )

    await context.bot.send_photo(
        uid,
        photo=WELCOME_IMAGE,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👨‍💻 Developer", url=DEVELOPER_LINK)],
            [InlineKeyboardButton("💬 Support", url=SUPPORT_LINK)]
        ])
    )

    await update.message.reply_text("👇 Select an option:", reply_markup=main_keyboard())
    await context.bot.send_message(LOG_CHANNEL_ID, f"👤 New user: {user.full_name} | ID: {uid}")
    # --- Subscribed Button Callback ---
async def joined_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await check_force_join(query.from_user.id, context.bot):
        await query.edit_message_text("✅ Subscribed! Now use /start again.")
    else:
        await query.answer("❌ You haven't joined all required channels.", show_alert=True)

# --- Send Random Media Helper ---
async def send_random(update, context, collection, seen_field):
    uid = update.effective_user.id

    if await db.banned.find_one({"_id": uid}):
        return await update.message.reply_text("❌ You are banned.")

    user_doc = await db.users.find_one({"_id": uid}) or {"points": 0}
    if not is_admin(uid) and user_doc.get("points", 0) < 1:
        return await update.message.reply_text("🥺 You don’t have enough coins. Refer or Buy some.")

    seen_doc = await db[seen_field].find_one({"_id": uid}) or {}
    seen = seen_doc.get("seen", [])

    doc = await db[collection].aggregate([
        {"$match": {"msg_id": {"$nin": seen}}},
        {"$sample": {"size": 1}}
    ]).to_list(length=1)

    if not doc:
        await db[seen_field].update_one({"_id": uid}, {"$set": {"seen": []}}, upsert=True)
        return await update.message.reply_text("📭 No more new content. Come back later!")

    msg_id = doc[0]["msg_id"]
    await context.bot.copy_message(uid, VAULT_CHANNEL_ID, msg_id)

    if not is_admin(uid):
        await db.users.update_one({"_id": uid}, {"$inc": {"points": -1}})
        points = (await db.users.find_one({"_id": uid})).get("points", 0)
        await update.message.reply_text(f"✅ Sent!\n💰 Remaining: {points} coins.")
    else:
        await update.message.reply_text("✅ Sent! (Admin, no coin cut)")

    await db[seen_field].update_one({"_id": uid}, {"$addToSet": {"seen": msg_id}}, upsert=True)

# --- Commands ---
async def video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_random(update, context, "videos", "user_videos")

async def photo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_random(update, context, "photos", "user_photos")

async def points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await db.users.find_one({"_id": uid})
    points = user.get("points", 0) if user else 0
    await update.message.reply_text(f"💰 You have {points} coins.")

async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={uid}"
    await update.message.reply_text(f"🔗 Your referral link:\n{link}")

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("📈 Payment Help", url=DEVELOPER_LINK)],
        [InlineKeyboardButton("💬 Contact Owner", url="https://t.me/PSYCHO_X_KING")]
    ]
    await update.message.reply_photo(
        photo="https://graph.org/file/0921938be954fb02160e8-6a599c5fb10268f7b2.jpg",
        caption="💸 Buy more coins now!\nContact the owner for safe transactions.",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# --- Admin Upload ---
async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    msg = update.message
    try:
        if msg.video:
            unique_id = msg.video.file_unique_id
            exists = await db.videos.find_one({"unique_id": unique_id})
            if not exists:
                fwd = await msg.forward(chat_id=VAULT_CHANNEL_ID)
                await db.videos.insert_one({
                    "msg_id": fwd.message_id,
                    "unique_id": unique_id
                })
                await msg.reply_text("✅ Video saved to vault.")
            else:
                await msg.reply_text("⚠️ Already in vault.")
        elif msg.photo:
            unique_id = msg.photo[-1].file_unique_id
            exists = await db.photos.find_one({"unique_id": unique_id})
            if not exists:
                fwd = await msg.forward(chat_id=VAULT_CHANNEL_ID)
                await db.photos.insert_one({
                    "msg_id": fwd.message_id,
                    "unique_id": unique_id
                })
                await msg.reply_text("✅ Photo saved to vault.")
            else:
                await msg.reply_text("⚠️ Already in vault.")
    except Exception as e:
        logger.error(f"[Upload Error] {e}")
        await msg.reply_text("❌ Upload failed.")

# --- Admin Panel ---
def get_admin_panel():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("💰 Manage Coins", callback_data="admin_coins")],
        [InlineKeyboardButton("❌ Ban User", callback_data="admin_ban")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🎁 Gift Points to All", callback_data="admin_gift")]
    ])

def back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]])

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Access denied.")
    await update.message.reply_text("🧑‍💻 Welcome to Admin Panel", reply_markup=get_admin_panel())

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    if not is_admin(uid):
        return await query.edit_message_text("❌ Not allowed.")

    if query.data == "admin_stats":
        total = await db.users.count_documents({})
        banned = await db.banned.count_documents({})
        await query.edit_message_text(
            f"📊 Stats:\n👥 Total Users: {total}\n🚫 Banned: {banned}",
            reply_markup=back_button()
        )
    elif query.data == "admin_coins":
        await query.edit_message_text("💰 Use:\n`/addpoints <user_id> <coins>`", parse_mode="Markdown", reply_markup=back_button())
    elif query.data == "admin_ban":
        await query.edit_message_text("❌ Use:\n`/ban <user_id>`\n`/unban <user_id>`", parse_mode="Markdown", reply_markup=back_button())
    elif query.data == "admin_broadcast":
        context.user_data.clear()
        context.user_data["awaiting_broadcast"] = True
        await query.edit_message_text("📢 Send the message to broadcast.", reply_markup=back_button())
    elif query.data == "admin_gift":
        logger.info("Gift mode ON")
        context.user_data.clear()
        context.user_data["awaiting_gift"] = True
        await query.edit_message_text("🎁 Send number of coins to gift all users.", reply_markup=back_button())
    elif query.data == "admin_back":
        await query.edit_message_text("🔙 Back to Admin Panel", reply_markup=get_admin_panel())

# --- Admin Manual Commands ---
async def addpoints_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if len(args) != 2 or not args[0].isdigit() or not args[1].isdigit():
        return await update.message.reply_text("⚠️ Usage: /addpoints <user_id> <coins>")
    uid, coins = int(args[0]), int(args[1])
    await db.users.update_one({"_id": uid}, {"$inc": {"points": coins}}, upsert=True)
    await update.message.reply_text(f"✅ Added {coins} coins to user {uid}")

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if len(args) != 1 or not args[0].isdigit():
        return await update.message.reply_text("⚠️ Usage: /ban <user_id>")
    uid = int(args[0])
    await db.banned.update_one({"_id": uid}, {"$set": {"status": "banned"}}, upsert=True)
    await update.message.reply_text(f"🚫 User {uid} has been banned.")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if len(args) != 1 or not args[0].isdigit():
        return await update.message.reply_text("⚠️ Usage: /unban <user_id>")
    uid = int(args[0])
    await db.banned.delete_one({"_id": uid})
    await update.message.reply_text(f"✅ User {uid} has been unbanned.")

# --- Admin Message Handlers ---
async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id) or not context.user_data.get("awaiting_broadcast"):
        return
    context.user_data["awaiting_broadcast"] = False
    total, failed = 0, 0
    async for user in db.users.find({}):
        try:
            await context.bot.send_message(user["_id"], update.message.text)
            total += 1
        except TelegramError:
            failed += 1
    await update.message.reply_text(f"✅ Broadcast Done!\n📤 Sent: {total}\n❌ Failed: {failed}")

async def handle_gift_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("handle_gift_points triggered")
    if not is_admin(update.effective_user.id):
        logger.info("Not admin")
        return
    if not context.user_data.get("awaiting_gift"):
        logger.info("awaiting_gift not set")
        return

    context.user_data["awaiting_gift"] = False

    try:
        coins = int(update.message.text)
    except ValueError:
        logger.warning("Invalid input")
        return await update.message.reply_text("❌ Invalid number of coins.")

    logger.info(f"Gifting {coins} coins to all users...")
    
    banned_ids = {doc["_id"] async for doc in db.banned.find({})}
    total = 0

    async for user in db.users.find({}):
        if user["_id"] in banned_ids:
            continue
        await db.users.update_one({"_id": user["_id"]}, {"$inc": {"points": coins}})
        total += 1

    await update.message.reply_text(f"✅ Gifted {coins} coins to {total} users.")
    logger.info(f"Gift success for {total} users.")

# --- MAIN BOT RUNNER ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("photo", photo_command))
    app.add_handler(CommandHandler("video", video_command))
    app.add_handler(CommandHandler("points", points_command))
    app.add_handler(CommandHandler("refer", refer_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("addpoints", addpoints_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))

    # Callback buttons
    app.add_handler(CallbackQueryHandler(joined_callback, pattern="check_joined"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))

    # Reply keyboard triggers
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)🏙 VIDEO"), video_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)📷 PHOTO"), photo_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)💰 POINTS"), points_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)💸 BUY"), buy_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)/refer"), refer_command))

    # Admin uploads
    app.add_handler(MessageHandler(filters.VIDEO | filters.PHOTO, auto_upload))

    # Admin input
    app.add_handler(MessageHandler(filters.TEXT & filters.ALL, handle_broadcast))
    app.add_handler(MessageHandler(filters.TEXT & filters.ALL, handle_gift_points))

    app.run_polling()

if __name__ == "__main__":
    main()
