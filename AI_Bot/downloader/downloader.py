"""Find every way to watch or download a movie.

This module asks each registered source what it can offer and puts
the results in order: direct downloads first, then free and
ad-supported streaming, then subscription, rent and buy.
"""

from downloader.sources import base
from downloader.sources.base import MovieOffer, sort_offers


def find_offers(movie: dict, kinds=None) -> list[MovieOffer]:
    """Offers for a movie, best first.

    A source that fails is skipped rather than breaking the whole
    lookup, so one dead provider never hides the others.

    `kinds` narrows the lookup to sources that can produce those kinds
    of offer. A direct download request then takes about four seconds
    instead of waiting on every streaming provider.
    """

    offers: list[MovieOffer] = []

    wanted = set(kinds) if kinds else None

    for source in base.all_sources():

        try:

            if wanted and source.kinds and not wanted.intersection(source.kinds):
                continue

            if not source.can_handle(movie):
                continue

            resolved = source.resolve(movie)

            if wanted:
                resolved = [offer for offer in resolved if offer.kind in wanted]

            offers.extend(resolved)

        except Exception as error:

            print(f"[{source.name}] lookup failed: {error}")

    return sort_offers(dedupe(offers))


def find_downloads(movie: dict) -> list[MovieOffer]:
    """Direct, legal download links only."""

    return find_offers(movie, kinds=("download",))


def dedupe(offers: list[MovieOffer]) -> list[MovieOffer]:
    """Drop repeated provider and kind pairs."""

    seen = set()
    unique = []

    for offer in offers:

        key = (offer.kind, offer.provider)

        if key in seen:
            continue

        seen.add(key)
        unique.append(offer)

    return unique


def split_offers(offers: list[MovieOffer]):
    """Separate the headline offers from the long tail.

    Returns `(primary, secondary)` where primary holds the direct
    downloads, the free and ad-supported providers and the store
    options, and secondary holds the generic platform search links.
    """

    primary = []
    secondary = []

    for offer in offers:

        if offer.kind in ("download", "free", "ads", "subscription", "rent", "buy"):

            if offer.kind in ("free", "ads") and offer.provider == "YouTube":
                secondary.append(offer)
                continue

            primary.append(offer)

        else:
            secondary.append(offer)

    return primary, secondary


def best_match(results: list[dict], query: str) -> dict | None:
    """Pick the most plausible title out of a TMDB result list.

    Prefers an exact title match, then the highest rated result.
    """

    if not results:
        return None

    wanted = query.strip().lower()

    for result in results:

        title = (result.get("title") or "").lower()
        original = (result.get("original_title") or "").lower()

        if wanted in (title, original):
            return result

    scored = sorted(
        results,
        key=lambda item: (
            (item.get("vote_average") or 0) * (item.get("vote_count") or 0),
            item.get("popularity") or 0,
        ),
        reverse=True,
    )

    return scored[0]
