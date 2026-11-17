"""Web pages for movie download lookups.

The movie logic lives in downloader.commands, shared with the (now
unused) Telegram bot. These routes simply render its text output so
the feature survives in the web-only deployment.
"""

from flask import Blueprint, render_template, request

from downloader import commands as movie_commands

bp = Blueprint("movies", __name__)


def _render(title: str, query: str, handler):
    """Look up a title and render the result page."""

    query = (query or "").strip()

    if not query:
        return render_template(
            "movie.html", mode=title, query="", result=None, hint=None
        )

    try:
        result = handler(query)
    except Exception as error:
        print(f"Movie web lookup failed: {error}")
        result = "Could not look that up right now. Please try again."

    return render_template(
        "movie.html", mode=title, query=query, result=result, hint=None
    )


@bp.route("/movies", methods=["GET"])
def movies_home():
    """The search form."""

    return render_template(
        "movie.html", mode="Movies", query="", result=None, hint=None
    )


@bp.route("/movie", methods=["GET"])
def movie():
    """Movie details plus a direct download link."""

    return _render("Movie details", request.args.get("q", ""), movie_commands.handle_movie)


@bp.route("/download", methods=["GET"])
def download():
    """Direct, legal download links."""

    return _render(
        "Free downloads", request.args.get("q", ""), movie_commands.handle_download
    )
