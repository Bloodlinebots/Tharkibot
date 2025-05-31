import os
import json
import random
import asyncio
import zipfile
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)

# ---------------- CONFIG ----------------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
VAULT_CHANNEL_ID = -1002624785490
FORCE_JOIN_CHANNEL = "bot_backup"
ADMIN_USER_ID = 7755789304
TERMS_LINK = "https://t.me/bot_backup/7"
DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK = "https://t.me/botmine_tech"
WELCOME_IMAGE = "https://files.catbox.moe/19j4mc.jpg"

VIDEO_FILE = "video_ids.json"
USER_FILE = "user_seen.json"
SUDO_FILE = "sudos.json"
BANNED_FILE = "banned.json"

cooldown_time = 8
cooldowns = {}

# ---------------- HELPERS ----------------
def load_json(file, default):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return default

def save_json(file, data):
    with open(file, "w") as f:
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

# ---------------- AUTO DELETE HELPER ----------------
def delete_after_delay(bot, chat_id, message_id, delay):
    import time

    time.sleep(delay)
    try:
        asyncio.run(bot.delete_message(chat_id=chat_id, message_id=message_id))
    except:
        pass

# ---------------- HANDLERS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if is_banned(uid):
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return

    # Force join channel check
    try:
        member = await context.bot.get_chat_member(f"@{FORCE_JOIN_CHANNEL}", uid)
        if member.status in ["left", "kicked"]:
            btn = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")]]
            )
            await update.message.reply_text(
                "🚫 You must join our channel to use this bot.\n\n"
                "⚠️ Note: If you leave the channel, you will be restricted from using the bot.\n\n"
                "✅ After joining, please use /start",
                reply_markup=btn,
            )
            return
    except Exception:
        pass

    # Log new user start in vault channel
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
        "This bot is only for file forwarding.\n"
        "If the file content contains adult videos, the bot holds no responsibility.\n"
        "Please read terms and conditions carefully."
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

    if is_banned(uid):
        await query.message.reply_text("🚫 You are banned from using this bot.")
        return

    now = asyncio.get_event_loop().time()
    if not is_admin(uid):
        if uid in cooldowns and cooldowns[uid] > now:
            wait = int(cooldowns[uid] - now)
            await query.message.reply_text(
                f"⏳ Please wait {wait} seconds before getting another video."
            )
            return
        cooldowns[uid] = now + cooldown_time

    seen = user_seen.get(str(uid), [])
    unseen = list(set(videos) - set(seen))

    if not unseen:
        await query.message.reply_text(
            "✅ You have watched all videos of our server 😅\nRestarting the list for you!"
        )
        user_seen[str(uid)] = []
        save_json(USER_FILE, user_seen)
        unseen = videos.copy()

    random.shuffle(unseen)

    for msg_id in unseen:
        try:
            sent = await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=VAULT_CHANNEL_ID,
                message_id=msg_id,
                protect_content=True,  # restrict forward/save
            )
            # Auto-delete after 3 hours (10800 seconds)
            threading.Thread(
                target=delete_after_delay,
                args=(context.bot, uid, sent.message_id, 10800),
                daemon=True,
            ).start()

            seen.append(msg_id)
            user_seen[str(uid)] = seen
            save_json(USER_FILE, user_seen)

            await query.message.reply_text(
                "Want another? 😈",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("📥 Get Another Video", callback_data="get_video")]]
                ),
            )
            return
        except Exception:
            if msg_id in videos:
                videos.remove(msg_id)
                save_json(VIDEO_FILE, videos)

    await query.message.reply_text(
        "⚠️ No videos available right now, please try later."
    )


async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        return

    if update.message.video:
        try:
            sent = await context.bot.copy_message(
                chat_id=VAULT_CHANNEL_ID,
                from_chat_id=update.message.chat_id,
                message_id=update.message.message_id,
            )
            videos.append(sent.message_id)
            save_json(VIDEO_FILE, videos)
            await update.message.reply_text("✅ Video uploaded and saved to vault.")
        except Exception:
            await update.message.reply_text("⚠️ Failed to upload.")


# ---------------- NEW CALLBACK for Help Button ----------------
async def show_privacy_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "/privacy - Use this to see bot's Terms and Conditions"
    )


# ---------------- /privacy COMMAND ----------------
async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.forward_message(
            chat_id=update.effective_chat.id, from_chat_id="@bot_backup", message_id=7
        )
    except Exception:
        await update.message.reply_text("⚠️ Failed to fetch privacy message.")


# ---------------- /help COMMAND ----------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("If you need any help then contact developer")


# ------------- ADMIN COMMANDS --------------

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("🚫 You are not authorized to use this command.")
        return

    text = update.message.text.partition(" ")[2]
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

    files_to_backup = [VIDEO_FILE, USER_FILE, SUDO_FILE, BANNED_FILE]
    zip_path = "backup.zip"
    try:
        with zipfile.ZipFile(zip_path, "w") as zipf:
            for f in files_to_backup:
                if os.path.exists(f):
                    zipf.write(f, arcname=os.path.basename(f))
        await context.bot.send_document(chat_id=uid, document=open(zip_path, "rb"))
        os.remove(zip_path)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Backup failed: {e}")


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
            save_json(VIDEO_FILE, videos)
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
        new_id = int(args[0])
        if new_id not in sudo_users:
            sudo_users.append(new_id)
            save_json(SUDO_FILE, sudo_users)
            await update.message.reply_text(f"✅ User {new_id} added to sudo users.")
        else:
            await update.message.reply_text("User is already a sudo user.")
    except Exception:
        await update.message.reply_text("Invalid user id.")


async def remove_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("🚫 Only admin can remove sudo users.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /rmsudo user_id")
        return

    try:
        rem_id = int(args[0])
        if rem_id in sudo_users:
            sudo_users.remove(rem_id)
            save_json(SUDO_FILE, sudo_users)
            await update.message.reply_text(f"✅ User {rem_id} removed from sudo users.")
        else:
            await update.message.reply_text("User is not a sudo user.")
    except Exception:
        await update.message.reply_text("Invalid user id.")


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
        ban_id = int(args[0])
        if ban_id not in banned_users:
            banned_users.append(ban_id)
            save_json(BANNED_FILE, banned_users)
            await update.message.reply_text(f"🚫 User {ban_id} banned.")
        else:
            await update.message.reply_text("User is already banned.")
    except Exception:
        await update.message.reply_text("Invalid user id.")


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
        unban_id = int(args[0])
        if unban_id in banned_users:
            banned_users.remove(unban_id)
            save_json(BANNED_FILE, banned_users)
            await update.message.reply_text(f"✅ User {unban_id} unbanned.")
        else:
            await update.message.reply_text("User is not banned.")
    except Exception:
        await update.message.reply_text("Invalid user id.")


# ---------------- MAIN ----------------
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ Unknown command.")


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("help", help_command))

    # Admin/Sudo commands
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("backup", backup))
    app.add_handler(CommandHandler("deletevideo", delete_video))
    app.add_handler(CommandHandler("addsudo", add_sudo))
    app.add_handler(CommandHandler("rmsudo", remove_sudo))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))

    # Callbacks
    app.add_handler(CallbackQueryHandler(callback_get_video, pattern="get_video"))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern="back_to_start"))
    app.add_handler(CallbackQueryHandler(show_privacy_info, pattern="show_privacy_info"))

    # Video upload auto save
    app.add_handler(MessageHandler(filters.VIDEO & filters.User(sudo_users), auto_upload))

    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    print("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
