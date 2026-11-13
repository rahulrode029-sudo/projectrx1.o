"""Tests for the combined scanner and the account heuristics."""

from security import account_checker, scanner


# =====================================================
# SCANNER
# =====================================================

def test_a_clean_message_passes():
    result = scanner.scan_text("are we still on for 5pm?")

    assert result.ok
    assert result.reasons == []


def test_a_spam_message_fails():
    result = scanner.scan_text(
        "CONGRATULATIONS you have won a free gift, claim your prize now"
    )

    assert not result.ok
    assert result.spam_score > 0


def test_a_message_with_a_private_link_fails():
    result = scanner.scan_text("look at http://192.168.1.1/admin")

    assert not result.ok
    assert result.unsafe_urls


def test_an_empty_message_passes():
    assert scanner.scan_text("").ok


def test_scanning_a_safe_url_passes():
    assert scanner.scan_url("https://example.com/movie.mp4").ok


def test_scanning_a_private_url_fails():
    result = scanner.scan_url("http://127.0.0.1/secret.mp4")

    assert not result.ok
    assert result.reason


def test_scanning_a_disallowed_file_type_fails():
    result = scanner.scan_url("https://example.com/payload.exe")

    assert not result.ok


# =====================================================
# ACCOUNT CHECKER
# =====================================================

def test_a_handful_of_normal_messages_is_low_risk():
    risk = account_checker.assess(
        [
            "are you free this evening?",
            "the meeting is at 5",
            "bring the documents please",
            "on my way",
        ]
    )

    assert risk.score == 0
    assert risk.level == "low"
    assert not risk.is_suspicious


def test_too_few_messages_is_low_risk():
    risk = account_checker.assess(["hello"])

    assert risk.score == 0


def test_repeated_messages_are_suspicious():
    risk = account_checker.assess(
        [
            "click here for your free prize http://x.example",
            "click here for your free prize http://x.example",
            "click here for your free prize http://x.example",
            "click here for your free prize http://x.example",
        ]
    )

    assert risk.is_suspicious
    assert risk.level in ("medium", "high")


def test_link_heavy_senders_are_flagged():
    risk = account_checker.assess(
        [
            "http://one.example",
            "http://two.example",
            "http://three.example",
            "http://four.example",
        ]
    )

    assert risk.score > 0
    assert "sends a lot of links" in risk.reasons
