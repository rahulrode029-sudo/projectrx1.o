"""Telegram helpers.

Everything that talks to Telegram goes through here so the message
limit, the splitting behaviour and the error handling are defined
once instead of in every handler.

Messages are sent as plain text. Telegram auto-links URLs in plain
messages, and plain text cannot be broken by a stray underscore or
asterisk in a movie title.
"""

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

TELEGRAM_MESSAGE_LIMIT = 4096


def split_text(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split text into chunks that each fit inside one Telegram message.

    Prefers to break on a newline, then a space, and only cuts mid-word
    when there is no other option.
    """

    if not text:
        return []

    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text

    while remaining:

        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        cut = remaining.rfind("\n", 0, limit)

        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit)

        if cut < limit // 2:
            cut = limit

        chunk = remaining[:cut].rstrip()

        if chunk:
            chunks.append(chunk)

        remaining = remaining[cut:].lstrip()

    return chunks


async def send_message(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup=None,
    reply_to_message_id: int | None = None,
):
    """Send text to a chat, splitting it if it is too long."""

    sent = []

    for chunk in split_text(text):

        try:
            message = await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id,
                parse_mode=None,
            )
            sent.append(message)

        except TelegramError as error:
            print(f"Telegram send failed: {error}")

            # The inline keyboard belongs to the last chunk, otherwise
            # a button would point at the wrong message.
            reply_markup = None

    return sent


async def reply(message, text: str, reply_markup=None):
    """Reply to the message that triggered the command."""

    return await send_message(
        message.get_bot(),
        message.chat_id,
        text,
        reply_markup=reply_markup,
        reply_to_message_id=message.message_id,
    )


async def answer(callback_query, text: str = "", show_alert: bool = False):
    """Acknowledge an inline button press."""

    try:
        await callback_query.answer(text, show_alert=show_alert)
    except TelegramError as error:
        print(f"Callback answer failed: {error}")


def mention(user) -> str:
    """A safe mention of a user."""

    if not user:
        return "there"

    name = (user.first_name or "").strip()

    return name or getattr(user, "username", "") or "there"
