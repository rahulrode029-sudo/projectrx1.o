"""Free and ad-supported streaming providers, taken from TMDB.

TMDB's watch-provider data is refreshed daily, so this stays current
without any scraping. The `free` and `ads` buckets are the ones that
matter here: they are the ways to watch a title without paying.
"""

from downloader.sources.base import MovieOffer, MovieSource, register
from downloader.search import providers_for_region


@register
class TmdbProviderSource(MovieSource):
    """Where the title streams free or with ads."""

    name = "tmdb"
    kinds = ("free", "ads")

    def resolve(self, movie: dict) -> list[MovieOffer]:

        providers = providers_for_region(movie["id"])

        link = providers.get("link") or ""

        offers: list[MovieOffer] = []

        for entry in providers.get("free") or []:

            name = entry.get("provider_name")

            if name:
                offers.append(
                    MovieOffer(
                        kind="free",
                        provider=name,
                        url=link,
                        note="Free to watch",
                    )
                )

        for entry in providers.get("ads") or []:

            name = entry.get("provider_name")

            if name:
                offers.append(
                    MovieOffer(
                        kind="ads",
                        provider=name,
                        url=link,
                        note="Free with ads",
                    )
                )

        return offers
