"""Free streaming platforms in India.

TMDB's provider list is the primary answer, but it only covers
titles the data partners have catalogued. This registry is the
fallback: for any title, these platforms are worth checking, because
they carry free ad-supported catalogues that TMDB sometimes misses.

The links go to each platform's own search for the title, so they
keep working as catalogues change.
"""

import re

from downloader.sources.base import MovieOffer, MovieSource, register

PLATFORMS = [
    {
        "name": "Amazon MX Player",
        "kind": "free",
        "url": "https://www.mxplayer.com/search?q={q}",
        "note": "Free with ads, large Hindi and regional library",
    },
    {
        "name": "ZEE5",
        "kind": "free",
        "url": "https://www.zee5.com/search?q={q}",
        "note": "Free selection, deepest regional catalogue",
    },
    {
        "name": "JioHotstar",
        "kind": "free",
        "url": "https://www.hotstar.com/search?q={q}",
        "note": "Free selection with ads",
    },
    {
        "name": "SonyLIV",
        "kind": "free",
        "url": "https://www.sonyliv.com/search?q={q}",
        "note": "Free selection with ads",
    },
    {
        "name": "TVF Play",
        "kind": "free",
        "url": "https://www.tvfplay.com/search?q={q}",
        "note": "Free, original series and films",
    },
    {
        "name": "ShemarooMe",
        "kind": "free",
        "url": "https://www.sharamoome.com/search?q={q}",
        "note": "Free, classic Bollywood",
    },
    {
        "name": "Airtel Xstream Play",
        "kind": "free",
        "url": "https://www.airtel.xstream.com/search?q={q}",
        "note": "Free selection with ads",
    },
    {
        "name": "Tubi",
        "kind": "ads",
        "url": "https://tubitv.com/search/{slug}",
        "note": "Free with ads",
    },
    {
        "name": "Plex",
        "kind": "ads",
        "url": "https://watch.plex.tv/search?q={q}",
        "note": "Free with ads",
    },
    {
        "name": "YouTube",
        "kind": "ads",
        "url": "https://www.youtube.com/results?search_query={q}+full+movie+official",
        "note": "Search official studio uploads",
    },
]


def _slug(text: str) -> str:
    """A URL-safe slug for a title."""

    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")

    return slug or "movie"


@register
class FreePlatformSource(MovieSource):
    """Links to the free platforms that carry the title."""

    name = "free_platforms"

    def resolve(self, movie: dict) -> list[MovieOffer]:

        title = movie.get("original_title") or movie.get("title") or ""

        if not title:
            return []

        quoted = title.replace('"', "")

        slug = _slug(title)

        offers: list[MovieOffer] = []

        for platform in PLATFORMS:

            url = platform["url"].format(q=quoted.replace(" ", "%20"), slug=slug)

            offers.append(
                MovieOffer(
                    kind=platform["kind"],
                    provider=platform["name"],
                    url=url,
                    note=platform["note"],
                )
            )

        return offers
