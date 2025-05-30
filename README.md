# TharkiHubBot

A Telegram bot that forwards random videos from a private channel with force join system.

## Features

- Sends a welcome message with a button to get random MMS videos.
- Forces users to join a specific Telegram channel before using the bot.
- Forwards random videos from a private vault channel.
- Simple and easy to deploy on Heroku.

## Setup

1. Replace the placeholders in `bot.py`:
   - `BOT_TOKEN` in your environment variables.
   - `VAULT_CHANNEL_ID` with your private channel ID.
   - `FORCE_JOIN_CHANNEL` with your Telegram channel username (without @).
   - `VIDEO_MESSAGE_IDS` with a list of message IDs containing videos.

2. Deploy on Heroku or your preferred platform.

## Usage

- Start the bot with `/start`.
- If not joined, bot asks to join the channel.
- After joining, tap the button to get random videos.

## Requirements

- python-telegram-bot==20.7
- Python 3.10+

---

Made with ❤️ by zeus
