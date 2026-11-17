"""Movie commands.

These functions return plain text that the Telegram handler sends.
Keeping them free of Telegram imports means they can be reused by
the web UI later.

The point of this bot is getting a film: direct, legal download links
come first, then free streaming. Pirate and camrip sources are never
used -- they break constantly and can get the bot and its accounts
banned.
"""

import re
from urllib.parse import quote

from downloader import downloader, search

# Free words that map onto TMDB genre ids.
MOOD_GENRES = {
    "scary": [27],
    "horror": [27],
    "creepy": [27],
    "spooky": [27],
    "thriller": [53],
    "suspense": [53],
    "funny": [35],
    "comedy": [35],
    "hilarious": [35],
    "fun": [35],
    "romance": [10749],
    "romantic": [10749],
    "love": [10749],
    "action": [28],
    "fighting": [28],
    "adventure": [12],
    "scifi": [878],
    "sci-fi": [878],
    "space": [878],
    "future": [878],
    "drama": [18],
    "emotional": [18],
    "family": [10751],
    "kids": [10751],
    "mystery": [9648],
    "whodunit": [9648],
    "fantasy": [14],
    "magic": [14],
    "documentary": [99],
    "docs": [99],
    "war": [10752],
    "crime": [80],
    "heist": [80],
    "animation": [16],
    "animated": [16],
    "cartoon": [16],
    "anime": [16],
    "music": [10402],
    "western": [37],
}

KIND_LABELS = {
    "download": "⬇ DOWNLOAD",
    "free": "▶ FREE",
    "ads": "▶ FREE WITH ADS",
    "subscription": "📺 SUBSCRIPTION",
    "rent": "💳 RENT",
    "buy": "💳 BUY",
}

# Plain language a user might type instead of a command. Checked before
# the message is handed to Gemini so a download request always lands
# here rather than getting a chat answer.
DOWNLOAD_PATTERNS = (
    re.compile(
        r"^\s*(?:please\s+)?(?:i\s+want\s+to\s+)?download\s+"
        r"(?:(?:the\s+)?movie\s+)?(.+?)\s*$",
        re.I,
    ),
    re.compile(r"^\s*(.+?)\s+download\s+link\s*$", re.I),
    re.compile(r"^\s*(.+?)\s+download\s*$", re.I),
    re.compile(r"^\s*(?:link|download\s+link)\s+for\s+(.+?)\s*$", re.I),
)

WATCH_PATTERNS = (
    re.compile(
        r"^\s*(?:where\s+(?:(?:can\s+i\s+)|to\s+)?(?:watch|see)|watch)\s+"
        r"(?:(?:the\s+)?movie\s+)?(.+?)\s*$",
        re.I,
    ),
)

# Chat words that mean a short message is a question, not a film title.
CHAT_MARKERS = {
    "hi", "hello", "hey", "thanks", "thank", "please", "help", "ok", "okay",
    "yes", "no", "how", "what", "why", "who", "when", "where", "which",
    "can", "could", "would", "should", "do", "does", "did", "is", "are",
    "was", "were", "tell", "give", "show", "want", "need", "i", "you",
    "my", "me", "we", "our", "your", "and", "or", "but", "sorry", "good",
    "bad", "morning", "evening", "night", "bye", "movie", "film", "song",
    "weather", "time", "date", "news", "translate", "joke", "story",
}


def looks_like_movie_title(text: str) -> bool:
    """Conservative check for a bare title like 'Interstellar'.

    A typed movie name should get a download link without the user
    having to remember a command. Anything that looks like a question
    or ordinary chat is left for Gemini instead.
    """

    text = (text or "").strip()

    if not text or len(text) > 70 or "?" in text or "@" in text:
        return False

    words = text.split()

    if not 1 <= len(words) <= 6:
        return False

    if any(word.lower().strip(".,!") in CHAT_MARKERS for word in words):
        return False

    # Titles are normally capitalised; lowercase phrases are usually chat.
    return any(word[:1].isupper() for word in words)


def _vote(value):
    return f"{value:.1f}" if value else "?"


def _year(movie):
    date = movie.get("release_date") or ""

    return date[:4] if date else "?"


def download_search_url(title: str) -> str:
    """An Internet Archive search for free copies of a title.

    Used where resolving an actual file for every film would be too
    slow (recommendation lists). The link is instant and always legal.
    """

    query = quote(f'collection:feature_films AND title:"{title}"')

    return f"https://archive.org/search?query={query}"


def text_request(text: str, patterns) -> str | None:
    """Return the title in a plain-language request, or None."""

    for pattern in patterns:
        match = pattern.match(text or "")

        if match:
            title = match.group(1).strip(" ?.!")

            if title:
                return title

    return None


def find_movie(query: str):
    """Look up a movie. Returns (movie, details) or (None, None)."""

    results = search.search_movies(query)

    match = downloader.best_match(results, query)

    if match is None:
        return None, None

    try:
        details = search.movie_details(match["id"])
    except Exception as error:
        print(f"Movie details failed: {error}")
        details = match

    return match, details


def movie_card(details: dict) -> str:
    """A readable summary of one movie."""

    lines = []

    title = details.get("title") or details.get("original_title") or "Unknown"

    lines.append(f"🎬 {title} ({_year(details)})")

    genres = [g["name"] for g in details.get("genres", []) if g.get("name")]

    runtime = details.get("runtime")

    meta = [f"⭐ {_vote(details.get('vote_average'))}"]

    if runtime:
        meta.append(f"{runtime} min")

    if genres:
        meta.append(", ".join(genres))

    lines.append("  " + "  •  ".join(meta))

    crew = details.get("credits", {}).get("crew", [])

    director = next(
        (c["name"] for c in crew if c.get("job") == "Director"), None
    )

    cast = [
        c["name"]
        for c in details.get("credits", {}).get("cast", [])[:3]
        if c.get("name")
    ]

    if director:
        lines.append(f"  🎬 Director: {director}")

    if cast:
        lines.append(f"  🎭 Cast: {', '.join(cast)}")

    overview = (details.get("overview") or "").strip()

    if overview:
        lines.append("")
        lines.append(overview)

    external = details.get("external_ids", {})

    if external.get("imdb_id"):
        lines.append("")
        lines.append(f"IMDb: https://www.imdb.com/title/{external['imdb_id']}/")

    return "\n".join(lines)


def format_downloads(title: str, downloads: list) -> str:
    """Render direct download links, the main purpose of the bot."""

    lines = [f"⬇ {title} - free download", ""]

    for index, offer in enumerate(downloads, start=1):
        note = f" ({offer.note})" if offer.note else ""

        lines.append(f"{index}. {offer.provider}{note}")
        lines.append(f"   {offer.url}")

    lines.append("")
    lines.append("Public domain or Creative Commons files. No signup needed.")

    return "\n".join(lines).strip()


def _free_streaming_lines(details: dict) -> list[str]:
    """Legal free ways to watch, for titles with no downloadable file."""

    lines = []

    try:
        providers = search.providers_for_region(details["id"])
    except Exception as error:
        print(f"Provider lookup failed: {error}")
        providers = {}

    entries = []

    for kind in ("free", "ads"):
        for entry in providers.get(kind) or []:
            name = entry.get("provider_name")

            if name and name not in entries:
                entries.append(name)

    lines.append("")

    if entries:
        lines.append("▶ Free to watch in India: " + ", ".join(entries))
    else:
        lines.append("No free streaming listed in India.")

    link = providers.get("link")

    if link:
        lines.append("All providers: " + link)

    return lines


def handle_movie(query: str) -> str:
    """The /movie command: details plus a direct download link first."""

    if not query:
        return "Usage: /movie <title>\nExample: /movie Interstellar"

    match, details = find_movie(query)

    if match is None:
        return f"🎬 No movie found for '{query}'."

    title = details.get("title") or query

    downloads = downloader.find_downloads(details)

    card = movie_card(details)

    if downloads:
        return card + "\n\n" + format_downloads(title, downloads)

    # Most new releases have no legal free download. Say so plainly,
    # then still give the free streaming options and an Archive search.
    text = card + f"\n\n⬇ No free legal download found for {title}."
    text += "\nPirate sites are illegal and break constantly - not linked here."
    text += "\n\nTry: " + download_search_url(title)

    return text + "\n" + "\n".join(_free_streaming_lines(details))


def handle_watch(query: str) -> str:
    """The /watch command - where the title can be streamed."""

    if not query:
        return "Usage: /watch <title>"

    match, details = find_movie(query)

    if match is None:
        return f"🎬 No movie found for '{query}'."

    providers = search.providers_for_region(details["id"])

    lines = [f"🎬 {details.get('title')} - where to watch", ""]

    found = False

    for kind, label in (
        ("free", "▶ FREE"),
        ("ads", "▶ FREE WITH ADS"),
        ("flatrate", "📺 SUBSCRIPTION"),
        ("rent", "💳 RENT"),
        ("buy", "💳 BUY"),
    ):

        entries = providers.get(kind) or []

        if not entries:
            continue

        found = True

        lines.append(f"{label}")
        lines.append(
            "  " + ", ".join(e.get("provider_name", "") for e in entries)
        )
        lines.append("")

    if not found:
        lines.append("No providers listed for this title in this region.")

    link = providers.get("link")

    if link:
        lines.append(f"Details: {link}")

    lines.append("")
    lines.append("Want a free download instead? Send /download <title>.")

    return "\n".join(lines).strip()


def handle_download(query: str) -> str:
    """The /download command - direct, legal download links first."""

    if not query:
        return "Usage: /download <title>"

    match, details = find_movie(query)

    if match is None:
        return f"🎬 No movie found for '{query}'."

    title = details.get("title") or query

    downloads = downloader.find_downloads(details)

    if downloads:
        text = format_downloads(title, downloads)
    else:
        text = f"⬇ {title}\n\nNo free legal download found."
        text += "\nPirate sites are illegal and break constantly - not linked here."
        text += "\n\nCheck the free archive: " + download_search_url(title)

    text += "\n" + "\n".join(_free_streaming_lines(details))

    return text


def _genres_for_mood(mood: str) -> list[int]:
    """Map free text onto TMDB genre ids."""

    text = (mood or "").lower()

    found = []

    for word, ids in MOOD_GENRES.items():

        if word in text:

            for genre_id in ids:
                if genre_id not in found:
                    found.append(genre_id)

    return found


def handle_recommend(mood: str = "") -> str:
    """The /recommend command - every suggestion gets a download link."""

    genres = _genres_for_mood(mood)

    if genres:
        movies = search.discover_by_genre(genres)
        heading = f"🎬 Because you want something {mood.strip()}"
    else:
        movies = search.trending_movies("week")
        heading = "🎬 Trending this week"

    if not movies:
        return "Could not find anything right now. Try again in a moment."

    lines = [heading, ""]

    for movie in movies[:8]:
        title = movie.get("title", "?")
        year = _year(movie)
        vote = _vote(movie.get("vote_average"))

        lines.append(f"• {title} ({year})  ⭐ {vote}")
        lines.append(f"  ⬇ Download: {download_search_url(title)}")

    lines.append("")
    lines.append("Send /download <title> for a direct file link when one exists.")

    return "\n".join(lines)


def handle_similar(query: str) -> str:
    """The /similar command."""

    if not query:
        return "Usage: /similar <title>"

    match, details = find_movie(query)

    if match is None:
        return f"🎬 No movie found for '{query}'."

    similar = search.similar_movies(details["id"])

    if not similar:
        return "Nothing similar found for that title."

    lines = [f"🎬 Movies like {details.get('title')}", ""]

    for movie in similar[:8]:
        title = movie.get("title", "?")

        lines.append(
            f"• {title} ({_year(movie)})  ⭐ {_vote(movie.get('vote_average'))}"
        )
        lines.append(f"  ⬇ Download: {download_search_url(title)}")

    lines.append("")
    lines.append("Send /download <title> for a direct file link when one exists.")

    return "\n".join(lines)
