import os
import json
import random
import time
import asyncio
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.error import BadRequest

# ---------------- CONFIG ---------------- #
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_USER_ID = 7755789304
VAULT_CHANNEL_ID = -1002572348022
FORCE_JOIN_CHANNEL = "bot_backup"
TERMS_LINK = "https://t.me/bot_backup/7"
DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK = "https://t.me/botmine_tech"

# ---------------- FILES ---------------- #
VIDEO_FILE = "video_ids.json"
SEEN_FILE = "user_seen.json"
BANNED_FILE = "banned_users.json"
SUDO_FILE = "sudo_users.json"

def load_json(filename, default):
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump(default, f)
    with open(filename) as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

def is_admin(user_id): return user_id == ADMIN_USER_ID
def is_sudo(user_id): return user_id == ADMIN_USER_ID or user_id in load_json(SUDO_FILE, [])
def is_banned(user_id): return user_id in load_json(BANNED_FILE, [])

def mark_seen(user_id, msg_id):
    seen = load_json(SEEN_FILE, {})
    seen.setdefault(str(user_id), []).append(msg_id)
    save_json(SEEN_FILE, seen)

def get_unseen(user_id):
    all_ids = load_json(VIDEO_FILE, [])
    seen = load_json(SEEN_FILE, {}).get(str(user_id), [])
    unseen = list(set(all_ids) - set(seen))
    if not unseen:
        save_json(SEEN_FILE, {**load_json(SEEN_FILE, {}), str(user_id): []})
        return "RESET"
    return random.choice(unseen)

async def is_user_joined(user_id, context):
    try:
        member = await context.bot.get_chat_member(f"@{FORCE_JOIN_CHANNEL}", user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

cooldowns = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if is_banned(user_id): return

    if not await is_user_joined(user_id, context):
        btn = InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")
        reply = InlineKeyboardMarkup([[btn]])
        await update.message.reply_text(
            "🚫 You must join our channel to use this bot.\n\n"
            "⚠️ Note: If you leave the channel, you will be restricted from using the bot.\n"
            "✅ After joining, please use /start",
            reply_markup=reply
        )
        return

    await context.bot.send_message(
        chat_id=ADMIN_USER_ID,
        text=f"🚀 User started bot:\nID: <code>{user_id}</code>\nName: @{user.username}" if user.username else user.full_name,
        parse_mode="HTML"
    )

    welcome_buttons = [
        [InlineKeyboardButton("Developer", url=DEVELOPER_LINK)],
        [InlineKeyboardButton("Support", url=SUPPORT_LINK)]
    ]
    await update.message.reply_photo(
        photo="https://files.catbox.moe/fxsuba.jpg",
        caption="🥵 Welcome to TharkiHub!\n👇 Tap below to explore:",
        reply_markup=InlineKeyboardMarkup(welcome_buttons)
    )

    await update.message.reply_text(
        "⚠️ Disclaimer:\nWe do not support or promote adult content.\n"
        "This bot contains 18+ content. Use at your own discretion.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📘 View Terms", url=TERMS_LINK)]])
    )

    await update.message.reply_text(
        "🔥 Want a random video? Tap below:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 Get Random Video", callback_data="get_video")]])
    )

async def video_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_banned(user_id): return

    if not await is_user_joined(user_id, context):
        join_btn = InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")
        await update.callback_query.message.reply_text("🚫 You must stay in our channel to use the bot.",
                                                       reply_markup=InlineKeyboardMarkup([[join_btn]]))
        return

    if not is_admin(user_id):
        now = time.time()
        if user_id in cooldowns and now - cooldowns[user_id] < 8:
            await update.callback_query.message.reply_text("⏳ Please wait 8 seconds.")
            return
        cooldowns[user_id] = now

    msg_id = get_unseen(user_id)
    if msg_id == "RESET":
        await update.callback_query.message.reply_text("✅ You have watched all videos! Restarting...")
        msg_id = random.choice(load_json(VIDEO_FILE, []))

    try:
        await context.bot.copy_message(update.effective_chat.id, VAULT_CHANNEL_ID, msg_id)
        mark_seen(user_id, msg_id)
    except:
        await update.callback_query.message.reply_text("⚠️ Video not found or deleted.")
        return

    await update.callback_query.message.reply_text("Want one more? 😈", reply_markup=InlineKeyboardMarkup(
        [[InlineKeyboardButton("📥 Get Another Video", callback_data="get_video")]]))

# ---------------- ADMIN/SUDO COMMANDS ---------------- #

async def add_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_sudo(update.effective_user.id): return
    video_ids = load_json(VIDEO_FILE, [])
    if update.message.reply_to_message and update.message.reply_to_message.video:
        msg_id = update.message.reply_to_message.message_id
    elif context.args and context.args[0].isdigit():
        msg_id = int(context.args[0])
    else:
        await update.message.reply_text("⚠️ Please reply to a video or give a message ID.")
        return
    if msg_id in video_ids:
        await update.message.reply_text("⚠️ This video is already in the list.")
    else:
        video_ids.append(msg_id)
        save_json(VIDEO_FILE, video_ids)
        await update.message.reply_text("✅ Video added successfully.")

async def delete_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_sudo(update.effective_user.id): return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to the video to delete it.")
        return
    msg_id = update.message.reply_to_message.message_id
    video_ids = load_json(VIDEO_FILE, [])
    if msg_id in video_ids:
        video_ids.remove(msg_id)
        save_json(VIDEO_FILE, video_ids)
        seen = load_json(SEEN_FILE, {})
        for uid in seen:
            seen[uid] = [v for v in seen[uid] if v != msg_id]
        save_json(SEEN_FILE, seen)
        await update.message.reply_text("✅ Video removed.")
    else:
        await update.message.reply_text("⚠️ This video is not in the list.")

async def delete_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    save_json(VIDEO_FILE, [])
    save_json(SEEN_FILE, {})
    await update.message.reply_text("✅ All videos and user history cleared.")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_sudo(update.effective_user.id): return
    if not context.args: return
    user_id = int(context.args[0])
    banned = load_json(BANNED_FILE, [])
    if user_id not in banned:
        banned.append(user_id)
        save_json(BANNED_FILE, banned)
        await update.message.reply_text("✅ User banned.")
    else:
        await update.message.reply_text("⚠️ Already banned.")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_sudo(update.effective_user.id): return
    if not context.args: return
    user_id = int(context.args[0])
    banned = load_json(BANNED_FILE, [])
    if user_id in banned:
        banned.remove(user_id)
        save_json(BANNED_FILE, banned)
        await update.message.reply_text("✅ User unbanned.")
    else:
        await update.message.reply_text("⚠️ Not in banned list.")

async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_sudo(update.effective_user.id): return
    videos = load_json(VIDEO_FILE, [])
    seen = load_json(SEEN_FILE, {})
    banned = load_json(BANNED_FILE, [])
    sudo = load_json(SUDO_FILE, [])
    total_seen = sum(len(v) for v in seen.values())
    await update.message.reply_text(
        f"📊 Bot Stats:\n\n📦 Total Videos: {len(videos)}\n"
        f"👤 Total Users: {len(seen)}\n👁️ Seen Entries: {total_seen}\n"
        f"⛔ Banned Users: {len(banned)}\n🧑‍💻 Sudo Users: {len(sudo)}"
    )

async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_sudo(update.effective_user.id): return
    t = time.ctime(os.path.getmtime(__file__))
    await update.message.reply_text(f"🛠 Bot Panel:\n\n📁 Vault: {len(load_json(VIDEO_FILE, []))} videos\n"
                                    f"🧑‍💻 Sudo: {len(load_json(SUDO_FILE, []))}\n⏱ Last Restart: {t}")

async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_document(InputFile(VIDEO_FILE))
    await update.message.reply_document(InputFile(SEEN_FILE))

async def addsudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args: return
    uid = int(context.args[0])
    sudo = load_json(SUDO_FILE, [])
    if uid not in sudo:
        sudo.append(uid)
        save_json(SUDO_FILE, sudo)
        await update.message.reply_text("✅ Sudo added.")

async def delsudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args: return
    uid = int(context.args[0])
    sudo = load_json(SUDO_FILE, [])
    if uid in sudo:
        sudo.remove(uid)
        save_json(SUDO_FILE, sudo)
        await update.message.reply_text("✅ Sudo removed.")

async def clean_dead(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_sudo(update.effective_user.id): return
    ids = load_json(VIDEO_FILE, [])
    alive = []
    for vid in ids:
        try:
            await context.bot.forward_message(update.effective_chat.id, VAULT_CHANNEL_ID, vid)
            alive.append(vid)
        except:
            continue
    save_json(VIDEO_FILE, alive)
    await update.message.reply_text(f"🧹 Cleaned list. {len(alive)} valid videos remain.")

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text("♻️ Restarting...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args: return
    text = ' '.join(context.args)
    users = load_json(SEEN_FILE, {}).keys()
    sent = 0
    for uid in users:
        try:
            await context.bot.send_message(int(uid), text)
            sent += 1
            await asyncio.sleep(0.2)
        except:
            continue
    await update.message.reply_text(f"📣 Broadcast sent to {sent} users.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_sudo(update.effective_user.id): return
    await update.message.reply_text(\"\"\"🤖 Bot Help:
    /start - Start bot
    /add_video - Add video (reply or msg_id)
    /delete_video - Delete video (reply)
    /delete_all - Clear all (admin)
    /ban /unban <id> - Ban/unban user
    /stat - Show stats
    /panel - Bot info
    /addsudo /delsudo <id>
    /backup - Get backup (admin)
    /clean_dead - Remove deleted videos
    /broadcast <msg> - Admin only
    /restart - Admin only\"\"\")

# ---------------- MAIN ---------------- #

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add_video", add_video))
    app.add_handler(CommandHandler("delete_video", delete_video))
    app.add_handler(CommandHandler("delete_all", delete_all))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("stat", stat))
    app.add_handler(CommandHandler("panel", panel))
    app.add_handler(CommandHandler("backup", backup))
    app.add_handler(CommandHandler("addsudo", addsudo))
    app.add_handler(CommandHandler("delsudo", delsudo))
    app.add_handler(CommandHandler("clean_dead", clean_dead))
    app.add_handler(CommandHandler("restart", restart))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(video_callback, pattern="get_video"))
    app.add_handler(MessageHandler(filters.VIDEO, add_video))

    async def leave_if_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.chat.type in ["group", "supergroup"]:
            await update.message.reply_text("🚫 This bot does not support group chat. So take care.\n📞 Contact developer: @unbornvillian")
            await context.bot.leave_chat(update.message.chat_id)

    app.add_handler(MessageHandler(filters.ALL, leave_if_group))
    app.run_polling()

if __name__ == "__main__":
    main()
