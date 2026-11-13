"""Movie commands.

These functions return plain text that the Telegram handler sends.
Keeping them free of Telegram imports means they can be reused by
the web UI later.
"""

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


def _vote(value):
    return f"{value:.1f}" if value else "?"


def _year(movie):
    date = movie.get("release_date") or ""

    return date[:4] if date else "?"


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
        lines.append(f"  🎥 Director: {director}")

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


def format_offers(title: str, offers: list) -> str:
    """Render the watch and download options."""

    if not offers:
        return (
            f"📥 {title}\n\n"
            "No free or download options found for this title.\n"
            "Try /watch to see paid options too."
        )

    lines = [f"📥 {title} — watch & download", ""]

    current_kind = None

    for index, offer in enumerate(offers, start=1):

        if offer.kind != current_kind:

            current_kind = offer.kind

            lines.append("")
            lines.append(KIND_LABELS.get(offer.kind, offer.kind.upper()))
            lines.append("")

        note = f" — {offer.note}" if offer.note else ""

        lines.append(f"{index}. {offer.provider}{note}")

        if offer.url:
            lines.append(f"   {offer.url}")

    return "\n".join(lines).strip()


def handle_movie(query: str) -> str:
    """The /movie command."""

    if not query:
        return "Usage: /movie <title>\nExample: /movie Interstellar"

    match, details = find_movie(query)

    if match is None:
        return f"🔍 No movie found for '{query}'."

    return movie_card(details)


def handle_watch(query: str) -> str:
    """The /watch command — where the title can be streamed."""

    if not query:
        return "Usage: /watch <title>"

    match, details = find_movie(query)

    if match is None:
        return f"🔍 No movie found for '{query}'."

    providers = search.providers_for_region(details["id"])

    region = "IN"

    lines = [f"📺 {details.get('title')} — where to watch", ""]

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

    return "\n".join(lines).strip()


def handle_download(query: str) -> str:
    """The /download command — every way to get the film."""

    if not query:
        return "Usage: /download <title>"

    match, details = find_movie(query)

    if match is None:
        return f"🔍 No movie found for '{query}'."

    offers = downloader.find_offers(details)

    primary, secondary = downloader.split_offers(offers)

    text = format_offers(details.get("title", "This movie"), primary)

    if secondary:
        text += "\n\nAlso worth checking:"

        for offer in secondary:
            text += f"\n• {offer.provider} — {offer.url}"

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
    """The /recommend command."""

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

        overview = (movie.get("overview") or "").strip()

        lines.append(f"• {title} ({year})  ⭐ {vote}")

        if overview:
            lines.append(f"  {overview[:150]}")

    lines.append("")
    lines.append("Want one of these? Send /movie <title> for links.")

    return "\n".join(lines)


def handle_similar(query: str) -> str:
    """The /similar command."""

    if not query:
        return "Usage: /similar <title>"

    match, details = find_movie(query)

    if match is None:
        return f"🔍 No movie found for '{query}'."

    similar = search.similar_movies(details["id"])

    if not similar:
        return "Nothing similar found for that title."

    lines = [f"🎬 Movies like {details.get('title')}", ""]

    for movie in similar[:8]:
        lines.append(
            f"• {movie.get('title')} ({_year(movie)})  ⭐ {_vote(movie.get('vote_average'))}"
        )

    lines.append("")
    lines.append("Send /movie <title> for links to any of these.")

    return "\n".join(lines)
