"""Tests for the movie commands.

The bot's job is to hand out direct, legal download links. These tests
pin that down without touching the network.
"""

from downloader import commands
from downloader.sources.base import MovieOffer


DETAILS = {
    "id": 1,
    "title": "A Test Film",
    "original_title": "A Test Film",
    "release_date": "1931-01-01",
    "vote_average": 7.5,
    "vote_count": 100,
    "popularity": 10,
    "genres": [],
    "credits": {"crew": [], "cast": []},
}


class _FakeDownloadSource:
    name = "fake_download"
    kinds = ("download",)

    def can_handle(self, movie):
        return True

    def resolve(self, movie):
        return [
            MovieOffer(
                kind="download",
                provider="Internet Archive",
                url="https://archive.org/download/test/test.mp4",
                note="Direct file, 500 MB",
            )
        ]


class _FakeProviderSource:
    name = "fake_provider"
    kinds = ("free", "ads")

    def can_handle(self, movie):
        return True

    def resolve(self, movie):
        return []


def _install_sources(monkeypatch, sources):
    monkeypatch.setattr(commands.downloader.base, "all_sources", lambda: sources)


def test_find_downloads_skips_streaming_sources(monkeypatch):
    calls = []

    class _Tracker(_FakeDownloadSource):
        def resolve(self, movie):
            calls.append("download")
            return super().resolve(movie)

    class _Provider(_FakeProviderSource):
        def resolve(self, movie):
            calls.append("provider")
            return super().resolve(movie)

    _install_sources(monkeypatch, [_Provider(), _Tracker()])

    offers = commands.downloader.find_downloads(DETAILS)

    assert calls == ["download"]
    assert len(offers) == 1
    assert offers[0].kind == "download"


def test_handle_download_leads_with_the_direct_link(monkeypatch):
    _install_sources(monkeypatch, [_FakeDownloadSource(), _FakeProviderSource()])
    monkeypatch.setattr(commands, "find_movie", lambda q: (DETAILS, DETAILS))

    text = commands.handle_download("A Test Film")

    assert text.index("free download") < text.index("https://archive.org/download")
    assert "Direct file, 500 MB" in text


def test_handle_movie_includes_the_download_link(monkeypatch):
    _install_sources(monkeypatch, [_FakeDownloadSource()])
    monkeypatch.setattr(commands, "find_movie", lambda q: (DETAILS, DETAILS))

    text = commands.handle_movie("A Test Film")

    assert "https://archive.org/download/test/test.mp4" in text
    assert "A Test Film (1931)" in text


def test_no_free_download_is_explained_without_pirate_links(monkeypatch):
    _install_sources(monkeypatch, [_FakeProviderSource()])
    monkeypatch.setattr(commands, "find_movie", lambda q: (DETAILS, DETAILS))

    text = commands.handle_download("A Test Film")

    assert "No free legal download found" in text
    assert "archive.org/search" in text
    assert "torrent" not in text.lower()


def test_recommendations_carry_download_links(monkeypatch):
    monkeypatch.setattr(
        commands.search,
        "trending_movies",
        lambda period: [{"title": "A Test Film", "release_date": "1931-01-01", "vote_average": 7}],
    )

    text = commands.handle_recommend()

    assert "A Test Film" in text
    assert "⬇ Download: https://archive.org/search" in text


def test_plain_text_download_requests_are_recognised():
    assert commands.text_request("download Interstellar", commands.DOWNLOAD_PATTERNS) == "Interstellar"
    assert (
        commands.text_request("Interstellar download link", commands.DOWNLOAD_PATTERNS)
        == "Interstellar"
    )
    assert (
        commands.text_request("please download the movie Interstellar", commands.DOWNLOAD_PATTERNS)
        == "Interstellar"
    )
    assert commands.text_request("hello there", commands.DOWNLOAD_PATTERNS) is None


def test_plain_text_watch_requests_are_recognised():
    assert (
        commands.text_request("where to watch Interstellar", commands.WATCH_PATTERNS)
        == "Interstellar"
    )


def test_bare_movie_titles_are_detected():
    assert commands.looks_like_movie_title("Interstellar") is True
    assert commands.looks_like_movie_title("The Dark Knight") is True
    assert commands.looks_like_movie_title("how are you") is False
    assert commands.looks_like_movie_title("What is the time?") is False
    assert commands.looks_like_movie_title("hello") is False
