"""Actual downloadable film files from the Internet Archive.

The search needs care. A plain media search also returns trailers,
interviews and featurettes, and filtering on `year` throws away every
result because that field is sparsely indexed. The working recipe is:

  1. query `collection:feature_films AND title:"<title>"`
  2. fetch the item metadata
  3. require `feature_films` in its collections
  4. require a video file above the size floor

Step 3 is what separates a film from a trailer.
"""

import httpx

from downloader.sources.base import MovieOffer, MovieSource, register

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/{identifier}"

# A real feature film is comfortably above this; clips and trailers
# are not.
MIN_BYTES = 100 * 1024 * 1024

VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mpeg", ".mpg", ".m4v")

BLOCKED_TITLE_WORDS = (
    "trailer",
    "clip",
    "extrait",
    "interview",
    "featurette",
    "promo",
    "teaser",
    "behind the scenes",
    "opening",
    "ending",
    "episode",
    "soundtrack",
)


def _search(title: str) -> list[dict]:
    """Search the feature film collection for a title."""

    try:
        response = httpx.get(
            SEARCH_URL,
            params={
                "q": f'collection:feature_films AND title:"{title}"',
                "fl[]": ["identifier", "title", "item_size", "downloads"],
                "rows": 8,
                "output": "json",
            },
            timeout=30.0,
        )
        response.raise_for_status()

    except httpx.HTTPError:
        return []

    return response.json().get("response", {}).get("docs", [])


def _item_metadata(identifier: str) -> dict | None:
    """Fetch one item's metadata, or None if it cannot be read."""

    try:
        response = httpx.get(
            METADATA_URL.format(identifier=identifier), timeout=30.0
        )
        response.raise_for_status()

    except httpx.HTTPError:
        return None

    return response.json()


def _best_video(files: list[dict]) -> dict | None:
    """The largest video file in an item."""

    videos = [
        entry
        for entry in files
        if entry.get("name", "").lower().endswith(VIDEO_EXTENSIONS)
        and entry.get("size")
    ]

    if not videos:
        return None

    return max(videos, key=lambda entry: int(entry.get("size", 0)))


def _human_size(size: int) -> str:
    value = float(size)

    for unit in ("B", "KB", "MB", "GB", "TB"):

        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"

        value /= 1024

    return f"{value:.1f} TB"


@register
class InternetArchiveSource(MovieSource):
    """Direct download links for public domain and archived films."""

    name = "internet_archive"
    kinds = ("download",)

    def resolve(self, movie: dict) -> list[MovieOffer]:

        title = movie.get("original_title") or movie.get("title") or ""

        if not title:
            return []

        offers: list[MovieOffer] = []

        for entry in _search(title):

            identifier = entry.get("identifier")

            if not identifier:
                continue

            entry_title = (entry.get("title") or "").lower()

            if any(word in entry_title for word in BLOCKED_TITLE_WORDS):
                continue

            metadata = _item_metadata(identifier)

            if not metadata:
                continue

            collections = metadata.get("metadata", {}).get("collection") or []

            if isinstance(collections, str):
                collections = [collections]

            if not any("feature_films" in str(name) for name in collections):
                continue

            video = _best_video(metadata.get("files", []))

            if not video:
                continue

            size = int(video.get("size", 0))

            if size < MIN_BYTES:
                continue

            server = metadata.get("server", "")
            directory = metadata.get("dir", "")

            if not server or not directory:
                continue

            url = f"https://{server}{directory}/{video['name']}"

            url = url.replace(" ", "%20").replace("(", "%28").replace(")", "%29")

            offers.append(
                MovieOffer(
                    kind="download",
                    provider="Internet Archive",
                    url=url,
                    note=f"Direct file, {_human_size(size)}",
                )
            )

            break

        return offers
