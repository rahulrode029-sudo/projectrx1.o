"""Combined scanning of anything that arrives from outside.

`scan_text` is the one to use on a message: it runs the spam check
and the URL safety check together and gives one verdict.
"""

from dataclasses import dataclass, field

from security import file_checker, url_checker
from services import spam_detector


@dataclass
class ScanResult:
    """The outcome of scanning one piece of content."""

    ok: bool = True
    reasons: list[str] = field(default_factory=list)
    spam_score: int = 0
    unsafe_urls: list = field(default_factory=list)

    def __bool__(self):
        return self.ok

    @property
    def reason(self) -> str:
        return "; ".join(self.reasons)


def scan_text(text: str) -> ScanResult:
    """Scan a message for spam and unsafe links."""

    result = ScanResult()

    if not text:
        return result

    verdict = spam_detector.check_text(text)

    result.spam_score = verdict.score

    if verdict.is_spam:
        result.ok = False
        result.reasons.append(verdict.reason or "looks like spam")

    unsafe = spam_detector.check_urls(text)

    if unsafe:
        result.ok = False
        result.unsafe_urls = unsafe

        for url, reason in unsafe:
            result.reasons.append(f"{url}: {reason}")

    return result


def scan_url(url: str) -> ScanResult:
    """Check a single URL before fetching it."""

    result = ScanResult()

    verdict = url_checker.check_url(url)

    if not verdict.ok:
        result.ok = False
        result.reasons.append(verdict.reason)

        return result

    ok, reason = file_checker.check_download_url(url)

    if not ok:
        result.ok = False
        result.reasons.append(reason)

    return result


def scan_media(path: str) -> ScanResult:
    """Check a file that was written to disk."""

    result = ScanResult()

    ok, reason = file_checker.check_file(path)

    if not ok:
        result.ok = False
        result.reasons.append(reason)

    return result
