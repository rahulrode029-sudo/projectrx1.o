"""File safety checks for anything the bot downloads."""

import os

# Extensions we are willing to accept.
ALLOWED_EXTENSIONS = (
    ".mp4", ".mkv", ".avi", ".m4v", ".webm",
    ".mp3", ".m4a", ".wav", ".flac",
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".pdf", ".txt", ".epub",
)

# Media type prefixes accepted for each extension group.
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".m4v", ".webm")

DEFAULT_MAX_MB = 4096


def extension_of(path: str) -> str:
    """The lowercase extension of a path.

    Handles a bare extension such as '.mp4' as well as a full name,
    because os.path.splitext treats a leading dot as a hidden file
    and reports no extension at all.
    """

    name = os.path.basename(path or "")

    if not name:
        return ""

    root, extension = os.path.splitext(name)

    if not extension and name.startswith("."):
        return name.lower()

    return extension.lower()


def is_allowed_extension(path: str) -> bool:
    return extension_of(path) in ALLOWED_EXTENSIONS


def size_mb(path: str) -> float:
    """File size in megabytes, or 0 if it cannot be read."""

    try:
        return os.path.getsize(path) / (1024 * 1024)
    except OSError:
        return 0.0


def check_file(path: str, max_mb: int = DEFAULT_MAX_MB):
    """Check a downloaded file.

    Returns `(ok, reason)`.
    """

    if not path:
        return False, "no file path"

    if not os.path.exists(path):
        return False, "file does not exist"

    extension = extension_of(path)

    if not is_allowed_extension(path):
        return False, f"file type '{extension}' is not allowed"

    size = size_mb(path)

    if size <= 0:
        return False, "file is empty"

    if size > max_mb:
        return False, f"file is {size:.1f} MB, over the {max_mb} MB limit"

    return True, f"{size:.1f} MB"


def check_download_url(url: str):
    """Check a URL before downloading it.

    Returns `(ok, reason)`.
    """

    from security.url_checker import check_url

    verdict = check_url(url)

    if not verdict.ok:
        return False, verdict.reason

    extension = extension_of(url.split("?")[0])

    if extension and not is_allowed_extension(extension):
        return False, f"file type '{extension}' is not allowed"

    return True, ""
