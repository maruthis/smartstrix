from fastapi import HTTPException

from app.secret_text import contains_secret_shaped_text, redact_secret_shaped_text, reject_secret_shaped_text


def test_detects_bearer_and_provider_tokens():
    assert contains_secret_shaped_text("Use Authorization: Bearer test-token on the live URL.")
    assert contains_secret_shaped_text("ghp_" + "a" * 36)
    assert contains_secret_shaped_text("glpat-" + "b" * 20)
    assert contains_secret_shaped_text("api_key=supersecretvalue")
    assert not contains_secret_shaped_text("Focus on authorization checks around wallet transfer.")
    assert not contains_secret_shaped_text("")


def test_redact_replaces_secret_shapes():
    text = redact_secret_shaped_text("Authorization: Bearer abcdefghijklmnop")
    assert "abcdefghijklmnop" not in text
    assert "[REDACTED]" in text


def test_reject_raises_for_secret_shaped_notes():
    try:
        reject_secret_shaped_text("Cookie: session=abc")
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "credentials_not_allowed"


def test_reject_returns_stripped_plain_text():
    assert reject_secret_shaped_text("  look at IDOR  ") == "look at IDOR"
    assert reject_secret_shaped_text("   ") is None
