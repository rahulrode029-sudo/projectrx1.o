"""Telegram command handlers.

Each command is a small async function that returns text. The
handler layer sends whatever comes back, so the command functions
themselves stay easy to test.
"""

from telegram.ext import CommandHandler

from database.database import session_scope
from downloader import commands as movie_commands
from models import NOTIFY_MODES
from services import gemini, memory, telegram as telegram_service
from services import whatsapp as whatsapp_service

HELP_TEXT = """🎬 RX — your AI and movie assistant

Movies - free downloads first
/movie <title>      Details + free download link
/download <title>   Direct, legal download links
/recommend [mood]   Suggestions, each with a download link
/similar <title>    Like this one, with download links
/watch <title>      Free streaming options

Just type it - no command needed:
  download Interstellar
  Interstellar download link
  where to watch Interstellar

WhatsApp archive
/contacts           Everyone who has written to you
/msg <name>         Recent messages, summarised
/read <name>        The raw text, on request
/summary <name>     What a contact has been saying
/deleted            Messages that were deleted
/mode <name>        full | summary | silent

Other
/search <query>    Ask anything
/help              This list
"""


# =====================================================
# GENERAL
# =====================================================

async def cmd_start(update, context):

    user = update.effective_user

    with session_scope() as session:
        whatsapp_service.remember_owner(
            session,
            chat_id=update.effective_chat.id,
            username=getattr(user, "username", None),
            display_name=getattr(user, "first_name", None),
        )
        session.commit()

    await telegram_service.reply(
        update.effective_message,
        "Hello! I am RX.\n\n"
        "I can recommend and look up movies, and I keep a copy of the "
        "messages that reach your WhatsApp so a deleted message is never "
        "lost.\n\n"
        "Send /help to see everything I can do.",
    )


async def cmd_help(update, context):
    await telegram_service.reply(update.effective_message, HELP_TEXT)


async def cmd_search(update, context):

    query = " ".join(context.args).strip()

    if not query:
        await telegram_service.reply(
            update.effective_message, "Usage: /search <your question>"
        )
        return

    try:
        answer = gemini.ask(
            query,
            system=(
                "You are RX, a helpful personal assistant. Answer clearly "
                "and concisely. Reply in Marathi, Hindi or English to match "
                "the language the question was asked in."
            ),
        )
    except Exception as error:
        print(f"Gemini error: {error}")
        answer = "Sorry, I could not process that right now."

    await telegram_service.reply(update.effective_message, answer)


# =====================================================
# MOVIES
# =====================================================

async def cmd_movie(update, context):

    query = " ".join(context.args).strip()

    try:
        text = movie_commands.handle_movie(query)
    except Exception as error:
        print(f"Movie lookup failed: {error}")
        text = "Could not look that up right now. Try again in a moment."

    await telegram_service.reply(update.effective_message, text)


async def cmd_recommend(update, context):

    mood = " ".join(context.args).strip()

    try:
        text = movie_commands.handle_recommend(mood)
    except Exception as error:
        print(f"Recommendation failed: {error}")
        text = "Could not fetch suggestions right now."

    await telegram_service.reply(update.effective_message, text)


async def cmd_similar(update, context):

    query = " ".join(context.args).strip()

    try:
        text = movie_commands.handle_similar(query)
    except Exception as error:
        print(f"Similar lookup failed: {error}")
        text = "Could not look that up right now."

    await telegram_service.reply(update.effective_message, text)


async def cmd_watch(update, context):

    query = " ".join(context.args).strip()

    try:
        text = movie_commands.handle_watch(query)
    except Exception as error:
        print(f"Watch lookup failed: {error}")
        text = "Could not look that up right now."

    await telegram_service.reply(update.effective_message, text)


async def cmd_download(update, context):

    query = " ".join(context.args).strip()

    try:
        text = movie_commands.handle_download(query)
    except Exception as error:
        print(f"Download lookup failed: {error}")
        text = "Could not look that up right now."

    await telegram_service.reply(update.effective_message, text)


# =====================================================
# WHATSAPP ARCHIVE
# =====================================================

async def cmd_contacts(update, context):

    with session_scope() as session:

        contacts = memory.all_contacts(session)

        if not contacts:
            await telegram_service.reply(
                update.effective_message,
                "No contacts yet. The WhatsApp sidecar has not sent "
                "anything.",
            )
            return

        lines = ["👥 Contacts", ""]

        for contact in contacts:

            preference = memory.get_preference(session, contact)

            deleted_count = (
                session.query(memory.Message)
                .filter_by(contact_id=contact.id, is_deleted=True)
                .count()
            )

            line = f"• {contact.label}  [{preference.notify_mode}]"

            if deleted_count:
                line += f"  ⚰ {deleted_count} deleted"

            lines.append(line)

    await telegram_service.reply(update.effective_message, "\n".join(lines))


def _format_timestamp(value):
    if value is None:
        return "?"

    try:
        return value.strftime("%d %b %H:%M")
    except Exception:
        return str(value)


async def cmd_msg(update, context):

    if not context.args:
        await telegram_service.reply(
            update.effective_message, "Usage: /msg <contact name>"
        )
        return

    query = " ".join(context.args).strip()

    limit = 5

    with session_scope() as session:

        contact = memory.resolve_contact(session, query)

        if contact is None:
            await telegram_service.reply(
                update.effective_message,
                f"I do not have a contact called '{query}'.",
            )
            return

        messages = memory.recent_from(session, contact, limit=limit)

        if not messages:
            await telegram_service.reply(
                update.effective_message,
                f"No messages from {contact.label} yet.",
            )
            return

        lines = [f"💬 {contact.label} — last {len(messages)}", ""]

        for message in messages:

            text = message.summary or message.preview

            lines.append(f"• {_format_timestamp(message.sent_at)} — {text}")

            if message.is_deleted:
                lines.append("   ⚰ deleted")

        lines.append("")
        lines.append(f"Raw text: /read {contact.label}")

    await telegram_service.reply(update.effective_message, "\n".join(lines))


async def cmd_read(update, context):

    if not context.args:
        await telegram_service.reply(
            update.effective_message, "Usage: /read <contact name> [count]"
        )
        return

    args = list(context.args)

    limit = 5

    if len(args) > 1 and args[-1].isdigit():
        limit = min(int(args[-1]), 25)
        args = args[:-1]

    query = " ".join(args).strip()

    with session_scope() as session:

        contact = memory.resolve_contact(session, query)

        if contact is None:
            await telegram_service.reply(
                update.effective_message,
                f"I do not have a contact called '{query}'.",
            )
            return

        messages = memory.recent_from(session, contact, limit=limit)

        if not messages:
            await telegram_service.reply(
                update.effective_message,
                f"No messages from {contact.label} yet.",
            )
            return

        lines = [f"📩 {contact.label} — raw messages", ""]

        for message in messages:

            body = message.body or "(no text)"

            lines.append(f"• {_format_timestamp(message.sent_at)}")
            lines.append(body)

            if message.is_deleted:
                lines.append("   ⚰ this one was deleted")

            lines.append("")

    await telegram_service.reply(update.effective_message, "\n".join(lines))


async def cmd_summary(update, context):

    if not context.args:
        await telegram_service.reply(
            update.effective_message, "Usage: /summary <contact name>"
        )
        return

    query = " ".join(context.args).strip()

    with session_scope() as session:

        contact = memory.resolve_contact(session, query)

        if contact is None:
            await telegram_service.reply(
                update.effective_message,
                f"I do not have a contact called '{query}'.",
            )
            return

        messages = memory.recent_from(session, contact, limit=20)

        if not messages:
            await telegram_service.reply(
                update.effective_message,
                f"No messages from {contact.label} yet.",
            )
            return

        bodies = [
            message.body for message in messages if (message.body or "").strip()
        ]

    if not bodies:
        await telegram_service.reply(
            update.effective_message,
            f"{contact.label} has only sent media, nothing to summarise.",
        )
        return

    joined = "\n".join(f"- {body}" for body in bodies)

    try:
        summary = gemini.ask(
            f"Summarise what {contact.label} has been saying in the "
            f"messages below. Cover the main points and anything they "
            f"asked for. Reply with a short paragraph, no preamble.\n\n"
            f"{joined}"
        )
    except Exception as error:
        print(f"Summary failed: {error}")
        summary = "I could not summarise those messages right now."

    await telegram_service.reply(
        update.effective_message,
        f"📝 What {contact.label} has been saying\n\n{summary}",
    )


async def cmd_deleted(update, context):

    with session_scope() as session:

        messages = memory.list_deleted(session, limit=25)

        if not messages:
            await telegram_service.reply(
                update.effective_message,
                "No deleted messages recorded yet.",
            )
            return

        lines = ["⚰ Deleted messages", ""]

        for message in messages:

            label = message.contact.label if message.contact else "someone"

            body = message.summary or message.preview

            lines.append(
                f"• {label} — {_format_timestamp(message.sent_at)}\n  {body}"
            )

        lines.append("")
        lines.append("Full text: /read <name>")

    await telegram_service.reply(update.effective_message, "\n".join(lines))


async def cmd_mode(update, context):

    if len(context.args) < 2:
        await telegram_service.reply(
            update.effective_message,
            "Usage: /mode <contact name> full | summary | silent\n\n"
            "full    - show the message text\n"
            "summary - tell you what it said, without the text\n"
            "silent  - do not tell you anything until you ask",
        )
        return

    mode = context.args[-1].lower()
    query = " ".join(context.args[:-1]).strip()

    if mode not in NOTIFY_MODES:
        await telegram_service.reply(
            update.effective_message,
            f"'{mode}' is not a mode. Use one of: "
            + ", ".join(NOTIFY_MODES),
        )
        return

    with session_scope() as session:

        contact = memory.resolve_contact(session, query)

        if contact is None:
            await telegram_service.reply(
                update.effective_message,
                f"I do not have a contact called '{query}'.",
            )
            return

        changed = memory.set_notify_mode(session, contact, mode)

        session.commit()

        label = contact.label

    if not changed:
        await telegram_service.reply(
            update.effective_message, "Could not change the mode."
        )
        return

    await telegram_service.reply(
        update.effective_message,
        f"Set {label} to '{mode}'.",
    )


# =====================================================
# REGISTRY
# =====================================================

def build_command_handlers():
    """Every command handler, in the order Telegram should try them."""

    return [
        CommandHandler("start", cmd_start),
        CommandHandler("help", cmd_help),
        CommandHandler("search", cmd_search),
        CommandHandler("movie", cmd_movie),
        CommandHandler("recommend", cmd_recommend),
        CommandHandler("similar", cmd_similar),
        CommandHandler("watch", cmd_watch),
        CommandHandler("download", cmd_download),
        CommandHandler("contacts", cmd_contacts),
        CommandHandler("msg", cmd_msg),
        CommandHandler("read", cmd_read),
        CommandHandler("summary", cmd_summary),
        CommandHandler("deleted", cmd_deleted),
        CommandHandler("mode", cmd_mode),
    ]
