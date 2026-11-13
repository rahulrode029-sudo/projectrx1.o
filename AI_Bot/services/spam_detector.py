"""Spam and abuse detection.

Two jobs: keep the obvious junk out of the stored messages, and stop
the bot being used as a link relay.
"""

import re

from security.url_checker import check_url

# Repeated characters used to push a message past a length limit.
FLOOD_PATTERN = re.compile(r"(.)\1{15,}")

# The same character or word over and over.
REPEAT_PATTERN = re.compile(r"\b(\w+)(?:\s+\1){3,}", re.IGNORECASE)

URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)

# Words that almost always mean a scam message.
SPAM_WORDS = (
    "free gift",
    "winner",
    "you have won",
    "claim your prize",
    "click here now",
    "limited time offer",
    "double your money",
    "crypto giveaway",
    "telegram premium free",
    "free nitro",
    "investment opportunity",
    "send money",
    "wire transfer",
)

# Links to these are never worth following from a chat message.
SUSPICIOUS_DOMAINS = (
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "is.gd",
    "cutt.ly",
    "shorturl.at",
)


class SpamVerdict:
    """Why a message was flagged, if it was."""

    def __init__(self, is_spam=False, reason="", score=0):
        self.is_spam = is_spam
        self.reason = reason
        self.score = score

    def __bool__(self):
        return self.is_spam

    def __repr__(self):
        return f"<SpamVerdict spam={self.is_spam} score={self.score} reason={self.reason!r}>"


def spam_score(text: str) -> int:
    """A rough score for how spam-like the text is."""

    if not text:
        return 0

    lowered = text.lower()

    score = 0

    for word in SPAM_WORDS:

        if word in lowered:
            score += 3

    # Flooding and repetition are spam on their own, not only when
    # combined with a suspicious phrase.
    if FLOOD_PATTERN.search(text):
        score += 3

    if REPEAT_PATTERN.search(text):
        score += 3

    urls = URL_PATTERN.findall(text)

    if len(urls) > 3:
        score += 2

    for url in urls:

        for domain in SUSPICIOUS_DOMAINS:

            if domain in url.lower():
                score += 2
                break

    return score


def check_text(text: str) -> SpamVerdict:
    """Judge a message for spam."""

    score = spam_score(text)

    if score >= 3:
        return SpamVerdict(True, "looks like spam", score)

    return SpamVerdict(False, "", score)


def check_urls(text: str) -> list:
    """Return the URLs in a message that are unsafe to follow."""

    unsafe = []

    for url in URL_PATTERN.findall(text or ""):

        verdict = check_url(url)

        if not verdict.ok:
            unsafe.append((url, verdict.reason))

    return unsafe


def contains_url(text: str) -> bool:
    return bool(URL_PATTERN.search(text or ""))
