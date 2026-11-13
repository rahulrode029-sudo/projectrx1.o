"""Message routing and inline button handling."""

from telegram.ext import CallbackQueryHandler, MessageHandler, filters

from database.database import session_scope
from services import gemini, memory
from services import telegram as telegram_service

SYSTEM_PROMPT = (
    "You are RX, a helpful personal AI assistant.\n\n"
    "Your name is RX.\n\n"
    "- Understand the question before answering.\n"
    "- Give accurate and useful answers.\n"
    "- Explain difficult topics simply.\n"
    "- For technical questions, give practical examples.\n"
    "- Keep answers concise unless asked for detail.\n"
    "- Reply in Marathi, Hindi or English to match the question.\n"
    "- Do not invent information when you are unsure.\n"
    "- Be respectful and professional.\n"
    "- Do not claim to be Gemini unless asked about the underlying model."
)


async def handle_text(update, context):
    """Plain text messages are answered by Gemini."""

    message = update.effective_message

    text = message.text or message.caption or ""

    if not text.strip():
        return

    try:
        answer = gemini.ask(text, system=SYSTEM_PROMPT)
    except Exception as error:
        print(f"Gemini error: {error}")
        answer = "Sorry, I couldn't process that message."

    await telegram_service.reply(message, answer)


async def handle_callback(update, context):
    """Handle the buttons under a delete alert."""

    query = update.callback_query

    data = query.data or ""

    if data.startswith("wa_show:"):

        wa_message_id = data.split(":", 1)[1]

        with session_scope() as session:

            message = memory.get_message(session, wa_message_id)

            if message is None:
                await telegram_service.answer(query, "Message not found.")
                return

            label = message.contact.label if message.contact else "someone"

            body = message.body or "(no text)"

            sent_at = message.sent_at

        await telegram_service.answer(query, "Here it is.")

        await telegram_service.send_message(
            query.get_bot(),
            query.message.chat_id,
            f"🕵️ Deleted message from {label}"
            + (f" ({sent_at.strftime('%d %b %H:%M')})" if sent_at else "")
            + f"\n\n{body}",
        )

        return

    if data.startswith("wa_ignore:"):

        await telegram_service.answer(query, "Ignored.")

        try:
            await query.message.delete()
        except Exception:
            pass

        return

    await telegram_service.answer(query, "Unknown action.")


def build_handlers():
    """The non-command handlers."""

    return [
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
        CallbackQueryHandler(handle_callback),
    ]
