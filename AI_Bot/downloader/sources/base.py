"""The source-adapter seam for movie sources.

Every source implements `resolve()` and returns a list of
`MovieOffer`. Adding a new source means adding one file and
registering it -- no other part of the project changes.

A "movie" is the raw TMDB detail dict, so any source can read
`movie["id"]`, `movie["title"]`, `movie["original_title"]` and so on.
"""

from dataclasses import dataclass


# Lower rank sorts first when results are ordered.
KIND_ORDER = {
    "download": 0,
    "free": 1,
    "ads": 2,
    "subscription": 3,
    "rent": 4,
    "buy": 5,
}


@dataclass
class MovieOffer:
    """One way of getting the film."""

    kind: str  # download | free | ads | subscription | rent | buy
    provider: str
    url: str
    note: str = ""

    @property
    def rank(self) -> int:
        return KIND_ORDER.get(self.kind, 99)


class MovieSource:
    """Base class for a movie source."""

    name = "source"

    def can_handle(self, movie: dict) -> bool:
        """Whether this source can offer anything for this movie."""

        return True

    def resolve(self, movie: dict) -> list[MovieOffer]:
        """Find every offer this source knows about."""

        raise NotImplementedError


_REGISTRY: list[type[MovieSource]] = []


def register(source_class):
    """Class decorator that adds a source to the registry."""

    _REGISTRY.append(source_class)

    return source_class


def all_sources() -> list[MovieSource]:
    """Instantiate every registered source."""

    return [source_class() for source_class in _REGISTRY]


def sort_offers(offers: list[MovieOffer]) -> list[MovieOffer]:
    """Order offers so the free and downloadable ones come first."""

    return sorted(offers, key=lambda offer: (offer.rank, offer.provider))
