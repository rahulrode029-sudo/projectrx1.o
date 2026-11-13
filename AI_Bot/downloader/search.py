"""TMDB client.

TMDB is the source of truth for movie data: titles, ratings, cast,
release dates and — the part that matters most here — where each
title can be watched, including the free and ad-supported providers.

Region aware: every lookup uses `settings.watch_region` (India by
default) so "where can I watch this free" answers for the right
market.
"""

import time

import httpx

from config import settings

BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

RETRIES = 4


def _wait(attempt: int) -> None:
    """Back off between retries."""

    time.sleep(1.5 * (attempt + 1))


class TmdbError(Exception):
    """Raised when TMDB cannot be reached or the key is wrong."""


def _get(path, params=None):
    """Call a TMDB endpoint and return the decoded JSON.

    Retries on connection resets and on rate limiting, because the
    free tier is quick to throttle and a dropped connection should
    not surface as a failed command.
    """

    if not settings.has_tmdb:
        raise TmdbError("TMDB_API_KEY is not set in .env")

    query = dict(params or {})
    query["api_key"] = settings.tmdb_api_key
    query.setdefault("language", "en-IN")

    last_error = None

    for attempt in range(RETRIES):

        try:

            response = httpx.get(
                f"{BASE_URL}{path}", params=query, timeout=25.0
            )

            if response.status_code == 429:
                last_error = TmdbError("TMDB rate limit reached, try again shortly.")
                _wait(attempt)
                continue

            response.raise_for_status()

            return response.json()

        except httpx.HTTPStatusError as error:
            raise TmdbError(
                f"TMDB returned {error.response.status_code} for {path}"
            ) from error

        except httpx.HTTPError as error:
            last_error = TmdbError(f"Could not reach TMDB: {error}")
            _wait(attempt)

    raise last_error or TmdbError(f"Could not reach TMDB for {path}")


def search_movies(query, year=None, page=1):
    """Search movies by title.

    Returns the raw TMDB results list, best match first.
    """

    params = {"query": query, "page": page, "include_adult": "false"}

    if year:
        params["year"] = year

    data = _get("/search/movie", params)

    return data.get("results", [])


def movie_details(movie_id):
    """Full detail for one movie, including credits and videos."""

    return _get(
        f"/movie/{movie_id}",
        {"append_to_response": "credits,videos,external_ids,images"},
    )


def watch_providers(movie_id, region=None):
    """Where a movie can be watched, by monetization type.

    The response has one entry per country, each holding `free`,
    `ads`, `flatrate`, `rent` and `buy` lists.
    """

    data = _get(f"/movie/{movie_id}/watch/providers")

    return data.get("results", {})


def providers_for_region(movie_id, region=None):
    """The provider lists for one region only."""

    region = region or settings.watch_region

    results = watch_providers(movie_id, region)

    return results.get(region, {}) or results.get("US", {})


def similar_movies(movie_id, page=1):
    return _get(f"/movie/{movie_id}/similar", {"page": page}).get("results", [])


def recommendations(movie_id, page=1):
    return _get(f"/movie/{movie_id}/recommendations", {"page": page}).get(
        "results", []
    )


def trending_movies(window="week", page=1):
    return _get(f"/trending/movie/{window}", {"page": page}).get("results", [])


def discover_free(region=None, since=None, page=1, sort="popularity.desc"):
    """Movies that can be watched free or with ads in a region.

    `since` is an ISO date; only films released on or after it are
    returned.
    """

    region = region or settings.watch_region

    params = {
        "watch_region": region,
        "with_watch_monetization_types": "free|ads",
        "sort_by": sort,
        "page": page,
        "include_adult": "false",
    }

    if since:
        params["primary_release_date.gte"] = since

    return _get("/discover/movie", params).get("results", [])


def discover_by_genre(genre_ids, region=None, since=None, page=1):
    """Discover movies filtered by genre ids."""

    region = region or settings.watch_region

    params = {
        "watch_region": region,
        "with_genres": ",".join(str(g) for g in genre_ids),
        "sort_by": "popularity.desc",
        "page": page,
        "include_adult": "false",
    }

    if since:
        params["primary_release_date.gte"] = since

    return _get("/discover/movie", params).get("results", [])


GENRES = {
    28: "Action",
    12: "Adventure",
    16: "Animation",
    35: "Comedy",
    80: "Crime",
    99: "Documentary",
    18: "Drama",
    10751: "Family",
    14: "Fantasy",
    36: "History",
    27: "Horror",
    10402: "Music",
    9648: "Mystery",
    10749: "Romance",
    878: "Science Fiction",
    10770: "TV Movie",
    53: "Thriller",
    10752: "War",
    37: "Western",
}


def genre_ids_for(names):
    """Map genre names to TMDB ids, ignoring unknown ones."""

    wanted = {name.strip().lower() for name in names}

    return [
        genre_id
        for genre_id, genre_name in GENRES.items()
        if genre_name.lower() in wanted
    ]


def poster_url(movie):
    """Poster image URL, or None."""

    path = movie.get("poster_path")

    if not path:
        return None

    return f"{IMAGE_BASE}{path}"
