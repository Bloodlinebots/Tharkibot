import os
import json
import random
import threading
import asyncio
import zipfile
import tempfile
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
VAULT_CHANNEL_ID = -1002624785490
FORCE_JOIN_CHANNEL = "bot_backup"
ADMIN_USER_ID = 7755789304
DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK = "https://t.me/botmine_tech"
TERMS_LINK = "https://t.me/bot_backup/7"
WELCOME_IMAGE = "https://files.catbox.moe/19j4mc.jpg"

VIDEO_FILE = "video_ids.json"
USER_FILE = "user_seen.json"
SUDO_FILE = "sudos.json"
BANNED_FILE = "banned.json"

COOLDOWN = 8

# --------- HELPERS ------------

file_lock = threading.Lock()

def load_json(file, default):
    with file_lock:
        if os.path.exists(file):
            try:
                with open(file, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                backup_file = file + ".bak"
                if os.path.exists(backup_file):
                    try:
                        with open(backup_file, "r") as bf:
                            return json.load(bf)
                    except json.JSONDecodeError:
                        return default
                return default
        return default

def save_json(file, data):
    with file_lock:
        dir_name = os.path.dirname(file) or "."
        backup_file = file + ".bak"
        try:
            if os.path.exists(file):
                os.replace(file, backup_file)
        except Exception:
            pass

        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False) as tf:
            json.dump(data, tf, indent=2)
            tempname = tf.name
        os.replace(tempname, file)

videos = load_json(VIDEO_FILE, [])
user_seen = load_json(USER_FILE, {})
sudo_users = load_json(SUDO_FILE, [])
banned_users = load_json(BANNED_FILE, [])

cooldowns = {}

def is_admin(uid): return uid == ADMIN_USER_ID
def is_sudo(uid): return uid in sudo_users or is_admin(uid)
def is_banned(uid): return uid in banned_users

def delete_after_delay(bot, chat_id, message_id, delay):
    import time
    time.sleep(delay)
    try:
        asyncio.run(bot.delete_message(chat_id=chat_id, message_id=message_id))
    except Exception:
        pass

# --------- HANDLERS -----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if is_banned(uid):
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

    if is_banned(uid):
        await query.message.reply_text("🚫 You are banned from using this bot.")
        return

    now = asyncio.get_event_loop().time()
    if not is_admin(uid):
        if uid in cooldowns and cooldowns[uid] > now:
            wait = int(cooldowns[uid] - now)
            await query.message.reply_text(f"⏳ Please wait {wait} seconds before getting another video.")
            return
        cooldowns[uid] = now + COOLDOWN

    seen = user_seen.get(str(uid), [])
    unseen = list(set(videos) - set(seen))

    if not unseen:
        msg_flag_key = f"{uid}_msg_sent"
        if not user_seen.get(msg_flag_key, False):
            await query.message.reply_text(
                "✅ You have watched all videos on our server 😅\nRestarting the list for you!"
            )
            user_seen[msg_flag_key] = True
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
                protect_content=True,
            )
            threading.Thread(
                target=delete_after_delay,
                args=(context.bot, uid, sent.message_id, 10800),
                daemon=True,
            ).start()

            seen.append(msg_id)
            user_seen[str(uid)] = seen
            user_seen[f"{uid}_msg_sent"] = False
            save_json(USER_FILE, user_seen)

            total_videos = len(videos)
            watched = len(seen)
            await query.message.reply_text(
                f"🎬 Video {watched}/{total_videos} watched.\nWant another? 😈",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("📥 Get Another Video", callback_data="get_video")]]
                ),
            )
            return
        except Exception:
            if msg_id in videos:
                videos.remove(msg_id)
                save_json(VIDEO_FILE, videos)

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
                message_id=update.message.message_id,
            )
            videos.append(sent.message_id)
            save_json(VIDEO_FILE, videos)
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

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("🚫 You are not authorized.")
        return

    text = update.message.text.partition(" ")[2]
    if not text:
        await update.message.reply_text("Usage: /broadcast Your message here")
        return

    count = 0
    for user_id in user_seen.keys():
        if user_id.endswith("_msg_sent"):
            continue
        try:
            await context.bot.send_message(chat_id=int(user_id), text=text)
            count += 1
        except Exception:
            pass

    await update.message.reply_text(f"📣 Broadcast sent to {count} users.")

async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("🚫 You are not authorized.")
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

async def add_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("🚫 Only owner can add sudo.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /addsudo <user_id>")
        return

    try:
        new_sudo = int(context.args[0])
        if new_sudo not in sudo_users:
            sudo_users.append(new_sudo)
            save_json(SUDO_FILE, sudo_users)
            await update.message.reply_text(f"✅ Added {new_sudo} as sudo.")
        else:
            await update.message.reply_text("User already a sudo.")
    except ValueError:
        await update.message.reply_text("Invalid user ID.")

async def remove_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("🚫 Only owner can remove sudo.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /remsudo <user_id>")
        return

    try:
        rem_sudo = int(context.args[0])
        if rem_sudo in sudo_users:
            sudo_users.remove(rem_sudo)
            save_json(SUDO_FILE, sudo_users)
            await update.message.reply_text(f"✅ Removed {rem_sudo} from sudo.")
        else:
            await update.message.reply_text("User is not a sudo.")
    except ValueError:
        await update.message.reply_text("Invalid user ID.")

# --------- MAIN -----------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_get_video, pattern="get_video"))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern="back_to_start"))
    app.add_handler(CallbackQueryHandler(show_privacy_info, pattern="show_privacy_info"))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("backup", backup))
    app.add_handler(CommandHandler("addsudo", add_sudo))
    app.add_handler(CommandHandler("remsudo", remove_sudo))

    app.add_handler(MessageHandler(filters.VIDEO & filters.User(sudo_users + [ADMIN_USER_ID]), auto_upload))

    app.run_polling()

if __name__ == "__main__":
    main()
