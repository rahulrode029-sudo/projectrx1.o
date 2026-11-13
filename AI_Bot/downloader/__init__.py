"""Movie lookup, sources and download options.

    from downloader import search, downloader, commands
"""

from downloader.commands import (
    handle_download,
    handle_movie,
    handle_recommend,
    handle_similar,
    handle_watch,
    movie_card,
)
from downloader.downloader import best_match, find_offers, split_offers

__all__ = [
    "handle_download",
    "handle_movie",
    "handle_recommend",
    "handle_similar",
    "handle_watch",
    "movie_card",
    "best_match",
    "find_offers",
    "split_offers",
]
