"""Registered movie sources.

Importing this package registers every source with the registry in
`base.py`, so `base.all_sources()` finds them all.
"""

from downloader.sources import base
from downloader.sources.base import (
    KIND_ORDER,
    MovieOffer,
    MovieSource,
    all_sources,
    register,
    sort_offers,
)
from downloader.sources.free_platforms import FreePlatformSource
from downloader.sources.internet_archive import InternetArchiveSource
from downloader.sources.official_store import OfficialStoreSource
from downloader.sources.tmdb_free import TmdbProviderSource

__all__ = [
    "base",
    "KIND_ORDER",
    "MovieOffer",
    "MovieSource",
    "all_sources",
    "register",
    "sort_offers",
    "FreePlatformSource",
    "InternetArchiveSource",
    "OfficialStoreSource",
    "TmdbProviderSource",
]
