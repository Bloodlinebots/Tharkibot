import os
import asyncio
import logging
import time
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, User, Chat
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.error import BadRequest, TelegramError
from motor.motor_asyncio import AsyncIOMotorClient

# --- Configure logging ---
# Sets up basic logging to monitor the bot's operations and errors.
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
# Load sensitive data and configuration from environment variables.
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

# Static configuration values for the bot.
VAULT_CHANNEL_ID = -1002564608005  # Channel where videos are stored.
LOG_CHANNEL_ID = -1002624785490    # Channel for logging bot activities.
ADMIN_USER_ID = 7755789304         # Telegram user ID of the bot admin.
DEVELOPER_LINK = "https://t.me/PSYCHO_X_KING"
SUPPORT_LINK = "https://t.me/valahallah"
TERMS_LINK = "https://t.me/bot_backup/7"
WELCOME_IMAGE = "https://graph.org/file/d367814bc3243e72917ab-9f1d63e7b3f46b6716.jpg"

# List of channels users must join to use the bot.
FORCE_JOIN_CHANNELS = [
    {"type": "public", "username": "bot_backup", "name": "RASILI CHU💦"},
    {"type": "private", "chat_id": -1002799718375, "name": "RASMALAI🥵"},
    {"type": "public", "username": "valahallah", "name": "VALAHALLA🔥"},
]

# --- Optimized Database Connection ---
# Establishes a connection pool to MongoDB for efficient database access.
try:
    client = AsyncIOMotorClient(
        MONGO_URI,
        maxPoolSize=15,
        minPoolSize=5,
        connectTimeoutMS=30000,
        socketTimeoutMS=30000,
        serverSelectionTimeoutMS=30000
    )
    db = client["telegram_bot"]
    logger.info("Successfully connected to MongoDB.")
except Exception as e:
    logger.critical(f"Could not connect to MongoDB: {e}")
    exit(1)


# --- In-Memory Cache Implementation ---
class Cache:
    """A simple in-memory cache with Time-To-Live (TTL) support."""
    def __init__(self):
        self.data = {}
        self.ttl = {}

    def set(self, key, value, ttl=300):
        """Sets a key-value pair in the cache with a TTL."""
        self.data[key] = value
        self.ttl[key] = time.time() + ttl

    def get(self, key):
        """Gets a value from the cache if it exists and hasn't expired."""
        if key in self.data and time.time() < self.ttl.get(key, 0):
            return self.data[key]
        # Clean up expired key
        if key in self.data:
            self.delete(key)
        return None

    def delete(self, key):
        """Deletes a key from the cache."""
        self.data.pop(key, None)
        self.ttl.pop(key, None)

cache = Cache()

# --- Utility Functions ---
async def is_sudo(uid: int) -> bool:
    """Checks if a user has sudo privileges, using a cache."""
    cached = cache.get(f"sudo_{uid}")
    if cached is not None:
        return cached
    
    is_sudo_user = (uid == ADMIN_USER_ID) or await db.sudos.find_one({"_id": uid})
    cache.set(f"sudo_{uid}", bool(is_sudo_user), ttl=3600)
    return bool(is_sudo_user)

def main_keyboard() -> ReplyKeyboardMarkup:
    """Returns the main reply keyboard."""
    return ReplyKeyboardMarkup([
        ["🎥 Get Random Video"],
        ["ℹ️ Help", "📃 Terms"]
    ], resize_keyboard=True)

async def check_force_join(uid: int, bot) -> bool:
    """Checks if a user has joined all required channels, using a cache."""
    cached = cache.get(f"joined_{uid}")
    if cached is not None:
        return cached
    
    for channel in FORCE_JOIN_CHANNELS:
        try:
            chat_id = f"@{channel['username']}" if channel["type"] == "public" else channel["chat_id"]
            member = await bot.get_chat_member(chat_id, uid)
            if member.status in ["left", "kicked"]:
                cache.set(f"joined_{uid}", False, ttl=300) # Cache negative result
                return False
        except Exception as e:
            logger.error(f"Error checking channel {channel.get('name', 'N/A')}: {e}")
            return False # Fail safely
    
    cache.set(f"joined_{uid}", True, ttl=300) # Cache positive result
    return True

# --- Core Bot Logic ---

async def send_welcome_message(user: User, chat: Chat, context: ContextTypes.DEFAULT_TYPE):
    """Sends the standardized welcome message and keyboard."""
    bot_name = (await context.bot.get_me()).first_name
    caption = (
        f"*😈 WELCOME TO {bot_name}\\!*\\n"
        "Uncover the naughtiest unseen drops 💦 just for you\\.\\n"
        "👇 Smash the menu button and enjoy\\!\\n\n"
        "```⚡ Note: This is the official bot of the Vallalah Team.```"
    )
    
    # Send welcome photo with inline buttons
    await context.bot.send_photo(
        chat_id=chat.id,
        photo=WELCOME_IMAGE,
        caption=caption,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👨‍💻 Developer", url=DEVELOPER_LINK)],
            [InlineKeyboardButton("👥 Support", url=SUPPORT_LINK), InlineKeyboardButton("📃 Terms", url=TERMS_LINK)],
        ]),
        parse_mode="MarkdownV2"
    )
    
    # Send a follow-up message with the main reply keyboard
    await context.bot.send_message(
        chat_id=chat.id,
        text="👇 Choose from the menu:",
        reply_markup=main_keyboard()
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id

    # ✅ Handle /start video_<msg_id> link
    if context.args and context.args[0].startswith("video_"):
        try:
            msg_id = int(context.args[0].split("_", 1)[1])
            await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=VAULT_CHANNEL_ID,
                message_id=msg_id,
                protect_content=True
            )
            await context.bot.send_message(
                chat_id=uid,
                text="🎁 Here's the shared video! Enjoy 😈",
                reply_markup=main_keyboard()
            )
            return
        except Exception as e:
            logger.error(f"Error loading shared video: {e}")
            await update.message.reply_text("⚠️ Couldn't load the shared video.")
            return
        
    # Check if the user is banned
    banned = cache.get(f"banned_{uid}")
    if banned is None:
        banned = await db.banned.find_one({"_id": uid})
        cache.set(f"banned_{uid}", bool(banned), ttl=3600)
    if banned:
        await update.message.reply_text("❌ You are banned from using this bot.")
        return

    # Check if user has joined all required channels
    if not await check_force_join(uid, context.bot):
        buttons = []
        for ch in FORCE_JOIN_CHANNELS:
            try:
                if ch["type"] == "public":
                    url = f"https://t.me/{ch['username']}"
                else:
                    invite_link = await context.bot.create_chat_invite_link(
                        chat_id=ch["chat_id"],
                        expire_date=int(time.time()) + 86400,
                        creates_join_request=False
                    )
                    url = invite_link.invite_link
                buttons.append([InlineKeyboardButton(f"🔗 Join {ch['name']}", url=url)])
            except Exception as e:
                logger.error(f"Could not create invite link for {ch['name']}: {e}")

        buttons.append([InlineKeyboardButton("✅ I've Joined", callback_data="force_check")])
        await update.message.reply_text(
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
        return

    # Add new user to the database and log the event
    if not await db.users.find_one({"_id": uid}):
        await db.users.update_one({"_id": uid}, {"$set": {"name": user.full_name}}, upsert=True)
        asyncio.create_task(
            context.bot.send_message(
                LOG_CHANNEL_ID,
                f"👤 New user: {user.full_name} | ID: `{uid}`"
            )
        )

    await send_welcome_message(user, update.effective_chat, context)

async def get_random_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches and sends a random unseen video to the user."""
    uid = update.effective_user.id
    
    # Check if the user is banned
    if await db.banned.find_one({"_id": uid}):
        await update.message.reply_text("❌ You are banned from using this bot.")
        return

    # Get user's seen videos from cache or DB
    seen_videos = cache.get(f"seen_{uid}")
    if seen_videos is None:
        user_doc = await db.user_videos.find_one({"_id": uid})
        seen_videos = user_doc.get("seen", []) if user_doc else []
        cache.set(f"seen_{uid}", seen_videos, ttl=1800)

    # Fetch a random video ID that the user hasn't seen
    pipeline = [
        {"$match": {"msg_id": {"$nin": seen_videos}}},
        {"$sample": {"size": 1}}
    ]
    random_video_cursor = db.videos.aggregate(pipeline)
    doc_list = await random_video_cursor.to_list(length=1)

    if not doc_list:
        # If all videos are seen, reset the seen list
        await db.user_videos.update_one({"_id": uid}, {"$set": {"seen": []}}, upsert=True)
        cache.set(f"seen_{uid}", [], ttl=1800)
        await update.message.reply_text("🎉 You've seen all available videos! Your watch history has been reset. Try again!")
        return

    msg_id = doc_list[0]["msg_id"]

    try:
        # Copy the video to the user, ensuring it's sent before the confirmation
        await context.bot.copy_message(
            chat_id=uid,
            from_chat_id=VAULT_CHANNEL_ID,
            message_id=msg_id,
            protect_content=True
        )
         bot_username = (await context.bot.get_me()).username
        start_link = f"https://t.me/{bot_username}?start=video_{msg_id}"

        await context.bot.send_message(
            chat_id=uid,
            text=(
                "✅ Here's your random video.\n"
                f"🔗 *Share this link to send this exact video to friends:*\n`{start_link}`\n\n"
                "👇 Use the menu to get more!"
            ),
            reply_markup=main_keyboard(),
            parse_mode="Markdown"
        )
        
        # Update seen list in cache and DB
        seen_videos.append(msg_id)
        cache.set(f"seen_{uid}", seen_videos, ttl=1800)
        asyncio.create_task(db.user_videos.update_one(
            {"_id": uid},
            {"$addToSet": {"seen": msg_id}},
            upsert=True
        ))
        
    except BadRequest as e:
        if "message to copy not found" in str(e).lower():
            logger.warning(f"Broken video reference found: {msg_id}. Deleting.")
            await db.videos.delete_one({"msg_id": msg_id})
            await db.user_videos.update_many({}, {"$pull": {"seen": msg_id}})
            
            asyncio.create_task(context.bot.send_message(
                LOG_CHANNEL_ID,
                f"⚠️ Removed broken video link. MSG_ID: `{msg_id}`",
                parse_mode="Markdown"
            ))
            await get_random_video(update, context)
        else:
            logger.error(f"BadRequest error for user {uid}: {e}")
            await update.message.reply_text("⚠️ An error occurred while sending the video. Please try again.")
    except TelegramError as e:
        logger.error(f"Telegram error for user {uid}: {e}")
        if "bot was blocked by the user" not in str(e).lower():
           await update.message.reply_text("⚠️ A Telegram-related error occurred. Please try again.")
    except Exception as e:
        logger.error(f"Unexpected error in get_random_video: {e}")
    

async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sudo-only command to upload videos to the vault."""
    if not await is_sudo(update.effective_user.id):
        return

    if update.message.video:
        unique_id = update.message.video.file_unique_id
        
        if cache.get(f"video_{unique_id}") or await db.videos.find_one({"unique_id": unique_id}):
            await update.message.reply_text("⚠️ This video already exists in the vault.")
            return
            
        try:
            sent_message = await context.bot.forward_message(
                chat_id=VAULT_CHANNEL_ID,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id
            )
            await db.videos.insert_one({
                "msg_id": sent_message.message_id,
                "unique_id": unique_id
            })
            cache.set(f"video_{unique_id}", True, ttl=86400)
            await update.message.reply_text("✅ Video forwarded to the vault and added to the database.")
        except Exception as e:
            logger.error(f"Failed to upload video from {update.effective_user.id}: {e}")
            await update.message.reply_text(f"❌ Upload failed: {e}")


async def force_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'I've Joined' button press."""
    query = update.callback_query
    await query.answer()

    cache.delete(f"joined_{query.from_user.id}")
    
    if await check_force_join(query.from_user.id, context.bot):
        await query.message.delete()
        await send_welcome_message(query.from_user, query.message.chat, context)
    else:
        await query.answer("🚫 You still haven't joined all required channels. Please join them and try again.", show_alert=True)

# --- Command Handlers ---

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /help command and 'Help' button."""
    await update.message.reply_text(f"💬 For help or support, please contact the developer:\n{DEVELOPER_LINK}")

async def terms_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /terms and 'Terms' button by forwarding the terms message."""
    try:
        await context.bot.forward_message(
            chat_id=update.effective_chat.id,
            from_chat_id="@bot_backup",
            message_id=7,
        )
    except Exception as e:
        logger.error(f"Error forwarding terms: {e}")
        await update.message.reply_text(f"⚠️ Could not fetch terms. Please view them directly: {TERMS_LINK}")

# --- Admin Commands ---

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sudo-only command to get bot statistics."""
    if not await is_sudo(update.effective_user.id):
        return
    
    stats = cache.get("stats")
    if stats is None:
        users_count = await db.users.count_documents({})
        videos_count = await db.videos.count_documents({})
        banned_count = await db.banned.count_documents({})
        sudos_count = await db.sudos.count_documents({})
        stats = {
            'users': users_count,
            'videos': videos_count,
            'banned': banned_count,
            'sudos': sudos_count
        }
        cache.set("stats", stats, ttl=300)
    
    await update.message.reply_text(
        f"📊 *Bot Statistics:*\n"
        f"👥 Total Users: `{stats['users']}`\n"
        f"🎞️ Videos in Vault: `{stats['videos']}`\n"
        f"🚫 Banned Users: `{stats['banned']}`\n"
        f"🛡️ Sudo Users: `{stats['sudos']}`",
        parse_mode="Markdown"
    )

async def add_sudo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main admin only: Adds a user to the sudo list."""
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ This command is restricted to the main admin.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /addsudo <user_id>")
        return
    
    try:
        user_id = int(context.args[0])
        await db.sudos.update_one({"_id": user_id}, {"$set": {"_id": user_id}}, upsert=True)
        cache.delete(f"sudo_{user_id}") # Invalidate cache
        await update.message.reply_text(f"✅ User `{user_id}` has been promoted to sudo.", parse_mode="Markdown")
    except (ValueError, IndexError):
        await update.message.reply_text("Invalid User ID provided.")

async def remove_sudo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main admin only: Removes a user from the sudo list."""
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ This command is restricted to the main admin.")
        return
        
    if not context.args:
        await update.message.reply_text("Usage: /removesudo <user_id>")
        return

    try:
        user_id = int(context.args[0])
        if user_id == ADMIN_USER_ID:
            await update.message.reply_text("❌ You cannot remove the main admin.")
            return

        result = await db.sudos.delete_one({"_id": user_id})
        if result.deleted_count:
            cache.delete(f"sudo_{user_id}") # Invalidate cache
            await update.message.reply_text(f"✅ User `{user_id}` has been demoted.", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"⚠️ User `{user_id}` was not a sudo user.", parse_mode="Markdown")
    except (ValueError, IndexError):
        await update.message.reply_text("Invalid User ID provided.")

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sudo command: Bans a user."""
    if not await is_sudo(update.effective_user.id):
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /ban <user_id>")
        return

    try:
        user_id = int(context.args[0])
        if await is_sudo(user_id):
            await update.message.reply_text("❌ You cannot ban an admin.")
            return

        await db.banned.update_one({"_id": user_id}, {"$set": {"_id": user_id}}, upsert=True)
        cache.set(f"banned_{user_id}", True, ttl=3600) # Update cache immediately
        await update.message.reply_text(f"✅ User `{user_id}` has been banned.", parse_mode="Markdown")
    except (ValueError, IndexError):
        await update.message.reply_text("Invalid User ID provided.")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sudo command: Unbans a user."""
    if not await is_sudo(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
        
    try:
        user_id = int(context.args[0])
        result = await db.banned.delete_one({"_id": user_id})
        if result.deleted_count:
            cache.delete(f"banned_{user_id}") # Invalidate cache
            await update.message.reply_text(f"✅ User `{user_id}` has been unbanned.", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"⚠️ User `{user_id}` was not banned.", parse_mode="Markdown")
    except (ValueError, IndexError):
        await update.message.reply_text("Invalid User ID provided.")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sudo command: Broadcasts a message to all users."""
    if not await is_sudo(update.effective_user.id):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Usage: Reply to a message with /broadcast")
        return

    message_to_broadcast = update.message.reply_to_message
    status_message = await update.message.reply_text("📢 Starting broadcast...")
    
    users_cursor = db.users.find({}, {"_id": 1})
    user_ids = [user["_id"] for user in await users_cursor.to_list(length=None)]
    
    success_count = 0
    fail_count = 0
    
    for user_id in user_ids:
        try:
            await context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=message_to_broadcast.chat_id,
                message_id=message_to_broadcast.message_id
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Broadcast failed for user {user_id}: {e}")
            fail_count += 1
        await asyncio.sleep(0.1) # Avoid rate limits
        
    await status_message.edit_text(
    f"📢 Broadcasting complete!\n"
    f"✅ Sent to: {success_count} users\n"
    f"❌ Failed for: {fail_count} users"
)

# --- Error Handling ---

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log errors and notify the admin."""
    
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    try:
        error_message = (
            f"⚠️ An error occurred!\n\n"
            f"Error: `{context.error}`\n\n"
            f"Update: `{update}`"
        )
        if len(error_message) > 4096:
            error_message = error_message[:4000] + "...`"
        
        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=error_message,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Failed to send error notification to admin: {e}")

def main():
    """Starts the bot."""
    if not TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN environment variable not set. Exiting.")
        return

    application = Application.builder().token(TOKEN).connect_timeout(30).read_timeout(30).build()
    
    # --- Register handlers ---
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("terms", terms_command))
    
    # Admin Command Handlers
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("addsudo", add_sudo_command))
    application.add_handler(CommandHandler("removesudo", remove_sudo_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))


    # Callback query handler for the "I've Joined" button
    application.add_handler(CallbackQueryHandler(force_check_callback, pattern="^force_check$"))

    # Message handlers for reply keyboard buttons
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^🎥 Get Random Video$"), get_random_video))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)^ℹ️ Help$"), help_command))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)^📃 Terms$"), terms_command))
    
    # Message handler for video uploads by sudo users
    application.add_handler(MessageHandler(filters.VIDEO & ~filters.COMMAND, auto_upload))
    
    application.add_error_handler(error_handler)
    
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
    logger.info("Bot stopped.") 
