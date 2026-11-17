"""Buying and renting a title from an official store."""

from downloader.sources.base import MovieOffer, MovieSource, register
from downloader.search import providers_for_region


@register
class OfficialStoreSource(MovieSource):
    """Permanent purchase and rental options."""

    name = "official_store"
    kinds = ("rent", "buy")

    def resolve(self, movie: dict) -> list[MovieOffer]:

        providers = providers_for_region(movie["id"])

        link = providers.get("link") or ""

        offers: list[MovieOffer] = []

        for entry in providers.get("rent") or []:

            name = entry.get("provider_name")

            if name:
                offers.append(
                    MovieOffer(
                        kind="rent",
                        provider=name,
                        url=link,
                        note="Rent",
                    )
                )

        for entry in providers.get("buy") or []:

            name = entry.get("provider_name")

            if name:
                offers.append(
                    MovieOffer(
                        kind="buy",
                        provider=name,
                        url=link,
                        note="Buy permanently",
                    )
                )

        return offers
