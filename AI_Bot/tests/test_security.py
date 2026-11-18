"""Tests for the safety helpers."""

from security import file_checker, url_checker
from services import spam_detector


# =====================================================
# URL CHECKING
# =====================================================

def test_https_urls_are_allowed():
    assert url_checker.check_url("https://example.com/movie").ok


def test_non_http_schemes_are_refused():
    for url in ("file:///etc/passwd", "ftp://example.com", "javascript:alert(1)"):
        assert not url_checker.check_url(url).ok


def test_loopback_hosts_are_refused():
    assert not url_checker.check_url("http://127.0.0.1/admin").ok
    assert not url_checker.check_url("http://localhost/admin").ok


def test_private_ranges_are_refused():
    assert not url_checker.check_url("http://192.168.1.1/").ok
    assert not url_checker.check_url("http://10.0.0.5/").ok
    assert not url_checker.check_url("http://169.254.169.254/latest/meta-data").ok


def test_empty_urls_are_refused():
    assert not url_checker.check_url("").ok
    assert not url_checker.check_url("   ").ok


# =====================================================
# FILE CHECKING
# =====================================================

def test_allowed_extensions():
    assert file_checker.is_allowed_extension("movie.mp4")
    assert file_checker.is_allowed_extension("MOVIE.MKV")


def test_disallowed_extensions():
    assert not file_checker.is_allowed_extension("payload.exe")
    assert not file_checker.is_allowed_extension("script.sh")


def test_missing_files_are_refused():
    ok, reason = file_checker.check_file("/definitely/not/here.mp4")

    assert ok is False
    assert reason


# =====================================================
# SPAM DETECTION
# =====================================================

def test_normal_messages_are_not_spam():
    assert not spam_detector.check_text("are we still on for 5pm?").is_spam


def test_prize_scam_messages_are_spam():
    verdict = spam_detector.check_text(
        "CONGRATULATIONS you have won a free gift, claim your prize now"
    )

    assert verdict.is_spam


def test_flooding_is_spam():
    assert spam_detector.check_text("a" * 40).is_spam


def test_repeated_words_are_spam():
    assert spam_detector.check_text("buy buy buy buy").is_spam


def test_urls_are_found():
    assert spam_detector.contains_url("see https://example.com/x")


def test_unsafe_urls_are_reported():
    unsafe = spam_detector.check_urls("go to http://127.0.0.1/secret")

    assert unsafe
    assert "127.0.0.1" in unsafe[0][0]
