"""RX — the Telegram bot.

Run this as its own process:

    python telegram_bot.py

It long-polls Telegram for commands and answers. The Flask app in
app.py handles the web UI and receives WhatsApp events; both share
the same SQLite database.
"""

import os

from telegram.ext import Application

from config import settings
from database.database import init_db
from services import telegram as telegram_service
from telegram_handlers import commands as command_handlers
from telegram_handlers import handlers as message_handlers
from telegram_handlers import moderation


async def on_startup(app: Application):
    """Prepare the database before the bot starts answering."""

    init_db()

    print("Database ready.")


def build_application() -> Application:
    """Assemble the bot with every handler registered."""

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(on_startup)
        .build()
    )

    for handler in command_handlers.build_command_handlers():
        application.add_handler(handler)

    for handler in message_handlers.build_handlers():
        application.add_handler(handler)

    application.add_error_handler(on_error)

    return application


async def on_error(update, context):
    """Log errors instead of letting them kill the polling loop."""

    print(f"Bot error: {context.error}")

    if update and getattr(update, "effective_message", None):

        try:
            await telegram_service.reply(
                update.effective_message,
                "Something went wrong on my side. Please try again.",
            )
        except Exception:
            pass


def main():
    """Start the bot."""

    if not settings.has_telegram:
        print("ERROR: TELEGRAM_BOT_TOKEN is not found in .env")
        return

    if not settings.has_gemini:
        print("ERROR: Gemini_API_KEY is not found in .env")
        return

    application = build_application()

    print(" RX is running...")
    print(f"   chat model : {settings.gemini_chat_model}")
    print(f"   database   : {settings.db_path}")

    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
