import os import json import random import asyncio import time from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update from telegram.ext import ( Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters ) from telegram.error import BadRequest

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") VAULT_CHANNEL_ID = -1002572348022 FORCE_JOIN_CHANNEL = "sjsjsskrj" ADMIN_USER_IDS = [7755789304] LOGGER_GROUP_ID = your_logger_group_id

VIDEO_IDS_FILE = "video_ids.json" USER_SEEN_FILE = "user_seen.json" SUDO_FILE = "sudo_users.json" LAST_RESTART_FILE = "restart_time.txt"

last_sent_time = {}

------------------------ Helpers ------------------------

def load_json(filename, default): if not os.path.exists(filename): with open(filename, "w") as f: json.dump(default, f) with open(filename, "r") as f: return json.load(f)

def save_json(filename, data): with open(filename, "w") as f: json.dump(data, f, indent=2)

def get_unseen_video(user_id): all_ids = load_json(VIDEO_IDS_FILE, []) seen_map = load_json(USER_SEEN_FILE, {}) seen = seen_map.get(str(user_id), []) unseen = list(set(all_ids) - set(seen)) if not all_ids: return None if not unseen: # Reset user history seen_map[str(user_id)] = [] save_json(USER_SEEN_FILE, seen_map) unseen = all_ids.copy() return random.choice(unseen)

def mark_seen(user_id, msg_id): seen_map = load_json(USER_SEEN_FILE, {}) seen = seen_map.get(str(user_id), []) if msg_id not in seen: seen.append(msg_id) seen_map[str(user_id)] = seen save_json(USER_SEEN_FILE, seen_map)

def get_sudo_users(): return load_json(SUDO_FILE, [])

def save_sudo_users(users): save_json(SUDO_FILE, users)

def is_sudo(user_id: int): return user_id in ADMIN_USER_IDS or user_id in get_sudo_users()

------------------------ Join Check ------------------------

async def is_user_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool: try: member = await context.bot.get_chat_member(f"@{FORCE_JOIN_CHANNEL}", user_id) return member.status in ["member", "administrator", "creator"] except BadRequest: return False

------------------------ Start ------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): user_id = update.effective_user.id user = update.effective_user

# Log to logger group
mention = user.mention_html() if user.username else f"{user.first_name}"
log_msg = f"👤 <b>New User Started Bot:</b>\n• Name: {mention}\n• ID: <code>{user_id}</code>"
await context.bot.send_message(chat_id=LOGGER_GROUP_ID, text=log_msg, parse_mode='HTML')

# Force join check
if not await is_user_joined(user_id, context):
    join_button = InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")
    reply_markup = InlineKeyboardMarkup([[join_button]])
    reply = await update.message.reply_text(
        "🚫 You must join our channel to use this bot.\n👉 If you leave the channel later, you will be blocked again.",
        reply_markup=reply_markup
    )
    context.user_data["force_join_msg_id"] = reply.message_id
    return

old_msg_id = context.user_data.get("force_join_msg_id")
if old_msg_id:
    try:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=old_msg_id)
    except:
        pass
    await update.message.reply_text("✅ You have joined the channel.\nPlease send /start again.")
    context.user_data.pop("force_join_msg_id", None)
    return

welcome_buttons = [
    [InlineKeyboardButton("your_button_name 1", url="https://t.me/unbornvillian")],
    [InlineKeyboardButton("your_button_name 2", url="https://t.me/unbornvillian")]
]
await update.message.reply_photo(
    photo="https://files.catbox.moe/fxsuba.jpg",
    caption="🥵 Welcome to TharkiHub!\n👇 Tap below to explore:",
    reply_markup=InlineKeyboardMarkup(welcome_buttons)
)
video_btn = [[InlineKeyboardButton("📥 Get Random Video", callback_data="get_video")]]
await update.message.reply_text("🔥 Want a random video? Tap below:", reply_markup=InlineKeyboardMarkup(video_btn))
terms_text = "📜 Read our Terms and Conditions"
terms_button = [[InlineKeyboardButton("📘 View Terms", url="https://t.me/your_username")]]
await update.message.reply_text(terms_text, reply_markup=InlineKeyboardMarkup(terms_button))

------------------------ Button ------------------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query user_id = query.from_user.id await query.answer()

if not await is_user_joined(user_id, context):
    join_button = InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")
    await query.message.reply_text("🚫 You must join our channel to use this bot.\n👉 If you leave the channel later, you will be blocked again.", reply_markup=InlineKeyboardMarkup([[join_button]]))
    return

now = time.time()
if user_id in last_sent_time and now - last_sent_time[user_id] < 8:
    await query.message.reply_text("⏱ Please wait 8 seconds before requesting again.")
    return

last_sent_time[user_id] = now

msg_id = get_unseen_video(user_id)
if not msg_id:
    await query.message.reply_text("✅ You have watched all videos of our server. Enjoy! 😊")
    return

try:
    await context.bot.copy_message(chat_id=query.message.chat_id, from_chat_id=VAULT_CHANNEL_ID, message_id=msg_id)
    mark_seen(user_id, msg_id)
    keyboard = [[InlineKeyboardButton("📥 Get Another Video", callback_data="get_video")]]
    await query.message.reply_text("Want one more? 😈", reply_markup=InlineKeyboardMarkup(keyboard))
except BadRequest:
    await query.message.reply_text("⚠️ Error: Video not found or deleted.")

------------------------ Admin ------------------------

async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE): if not is_sudo(update.effective_user.id): return await update.message.reply_text("❌ Not a sudder")

videos = load_json(VIDEO_IDS_FILE, [])
users = load_json(USER_SEEN_FILE, {})
seen_count = sum(len(v) for v in users.values())
sudo_list = get_sudo_users()
text = f"📊 Bot Status:\n\n🎞 Total Videos: {len(videos)}\n👤 Total Users: {len(users)}\n👁 Total Views Served: {seen_count}\n\n👮 Admins:\n• Owner: {ADMIN_USER_IDS[0]}\n• Sudo: {', '.join(map(str, sudo_list)) if sudo_list else 'None'}"
await update.message.reply_text(text)

async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE): if not is_sudo(update.effective_user.id): return await update.message.reply_text("❌ Not a sudder")

await update.message.reply_document(document=open(VIDEO_IDS_FILE, "rb"))
await update.message.reply_document(document=open(USER_SEEN_FILE, "rb"))

async def clean_dead(update: Update, context: ContextTypes.DEFAULT_TYPE): if not is_sudo(update.effective_user.id): return await update.message.reply_text("❌ Not a sudder")

videos = load_json(VIDEO_IDS_FILE, [])
alive = []
for msg_id in videos:
    try:
        await context.bot.forward_message(chat_id=update.effective_chat.id, from_chat_id=VAULT_CHANNEL_ID, message_id=msg_id)
        alive.append(msg_id)
    except:
        pass
save_json(VIDEO_IDS_FILE, alive)
await update.message.reply_text(f"✅ Cleaned! Total valid videos: {len(alive)}")

async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE): if not is_sudo(update.effective_user.id): return await update.message.reply_text("❌ Not a sudder")

videos = load_json(VIDEO_IDS_FILE, [])
sudos = get_sudo_users()
restart_time = 'unknown'
if os.path.exists(LAST_RESTART_FILE):
    with open(LAST_RESTART_FILE) as f:
        restart_time = f.read().strip()
await update.message.reply_text(
    f"📟 Panel Info:\n\n🎞 Vault Size: {len(videos)}\n👑 Owner: {ADMIN_USER_IDS[0]}\n👥 Sudo Count: {len(sudos)}\n🔁 Last Restart: {restart_time}")

------------------------ Sudo ------------------------

async def add_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE): if update.effective_user.id not in ADMIN_USER_IDS: return await update.message.reply_text("❌ You are not authorized to manage sudo users.")

try:
    uid = int(context.args[0])
    sudos = get_sudo_users()
    if uid not in sudos:
        sudos.append(uid)
        save_sudo_users(sudos)
        await update.message.reply_text(f"✅ User {uid} added to sudo list.")
    else:
        await update.message.reply_text("⚠️ This user is already a sudo.")
except:
    await update.message.reply_text("⚠️ Usage: /addsudo <user_id>")

async def del_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE): if update.effective_user.id not in ADMIN_USER_IDS: return await update.message.reply_text("❌ You are not authorized to remove sudo users.")

try:
    uid = int(context.args[0])
    sudos = get_sudo_users()
    if uid in sudos:
        sudos.remove(uid)
        save_sudo_users(sudos)
        await update.message.reply_text(f"✅ User {uid} removed from sudo list.")
    else:
        await update.message.reply_text("⚠️ This user is not in sudo list.")
except:
    await update.message.reply_text("⚠️ Usage: /delsudo <user_id>")

------------------------ Upload ------------------------

async def upload_video(update: Update, context: ContextTypes.DEFAULT_TYPE): if not is_sudo(update.effective_user.id): return await update.message.reply_text("❌ You are not authorized.")

if not update.message.video:
    return await update.message.reply_text("⚠️ Please send a video.")

try:
    sent = await context.bot.copy_message(chat_id=VAULT_CHANNEL_ID, from_chat_id=update.message.chat_id, message_id=update.message.message_id)
    video_ids = load_json(VIDEO_IDS_FILE, [])
    if sent.message_id not in video_ids:
        video_ids.append(sent.message_id)
        save_json(VIDEO_IDS_FILE, video_ids)
        await update.message.reply_text("✅ Video uploaded and saved.")
    else:
        await update.message.reply_text("⚠️ Already exists.")
except Exception as e:
    await update.message.reply_text(f"❌ Failed: {e}")

------------------------ Main ------------------------

def main(): with open(LAST_RESTART_FILE, "w") as f: f.write(time.strftime("%Y-%m-%d %H:%M:%S"))

application = Application.builder().token(TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button_handler, pattern="get_video"))
application.add_handler(CommandHandler("stat", stat))
application.add_handler(CommandHandler("backup", backup))
application.add_handler(CommandHandler("clean_dead", clean_dead))
application.add_handler(CommandHandler("panel", panel))
application.add_handler(CommandHandler("addsudo", add_sudo))
application.add_handler(CommandHandler("delsudo", del_sudo))
application.add_handler(CommandHandler("upload", upload_video))

application.run_polling()

if name == "main": main()

