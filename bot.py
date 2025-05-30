import os
import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import BadRequest

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
VAULT_CHANNEL_ID = -1002572348022 # Replace with your private channel ID
FORCE_JOIN_CHANNEL = "sjsjsskrj"  # Replace with your channel username (without @)
VIDEO_MESSAGE_IDS = [7,10]  # Replace with your video message IDs

async def is_user_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=f"@{FORCE_JOIN_CHANNEL}", user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except BadRequest:
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_joined(user_id, context):
        join_button = InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")
        reply_markup = InlineKeyboardMarkup([[join_button]])
        await update.message.reply_text("🚫 You must join our channel to use this bot.", reply_markup=reply_markup)
        return

    keyboard = [[InlineKeyboardButton("📥 Get Random MMS Video", callback_data="get_video")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🥵 Welcome to TharkiHub!\nTap below to get your random clip:", reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not await is_user_joined(user_id, context):
        join_button = InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")
        reply_markup = InlineKeyboardMarkup([[join_button]])
        await query.message.reply_text("🚫 You must join our channel to use this bot.", reply_markup=reply_markup)
        await query.answer()
        return

    await query.answer()
    msg_id = random.choice(VIDEO_MESSAGE_IDS)
    await context.bot.copy_message(
        chat_id=query.message.chat_id,
        from_chat_id=VAULT_CHANNEL_ID,
        message_id=msg_id
    )
    keyboard = [[InlineKeyboardButton("📥 Get Another MMS Video", callback_data="get_video")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Want one more? 😈", reply_markup=reply_markup)

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler, pattern="get_video"))
    application.run_polling()

if __name__ == "__main__":
    main()
