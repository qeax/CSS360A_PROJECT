"""Tests for listing HTML sanitization."""

from app.services.html_sanitize import sanitize_listing_html


def test_sanitize_strips_script_tags():
    raw = "<p>Hello</p><script>alert(1)</script>"
    cleaned = sanitize_listing_html(raw)
    assert "<script" not in cleaned.lower()
    assert "Hello" in cleaned


def test_sanitize_strips_onclick_handlers():
    raw = '<div onclick="evil()">Click</div>'
    cleaned = sanitize_listing_html(raw)
    assert "onclick" not in cleaned.lower()
    assert "Click" in cleaned


def test_sanitize_allows_basic_formatting():
    raw = "<p><strong>Bold</strong> and <em>italic</em></p>"
    cleaned = sanitize_listing_html(raw)
    assert "<strong>" in cleaned
    assert "<em>" in cleaned


def test_sanitize_allows_inline_style():
    raw = '<p style="color: red; font-weight: bold;">Styled</p>'
    cleaned = sanitize_listing_html(raw)
    assert "Styled" in cleaned
    assert "color" in cleaned
    assert "red" in cleaned


def test_sanitize_allows_style_tag():
    raw = "<style>p { color: blue; }</style><p>Blue text</p>"
    cleaned = sanitize_listing_html(raw)
    assert "<style" in cleaned.lower()
    assert "color" in cleaned
    assert "blue" in cleaned
    assert "Blue text" in cleaned


def test_sanitize_strips_javascript_urls():
    raw = '<a href="javascript:alert(1)">bad link</a>'
    cleaned = sanitize_listing_html(raw)
    assert "javascript:" not in cleaned.lower()


def test_sanitize_empty_returns_empty():
    assert sanitize_listing_html("") == ""
    assert sanitize_listing_html(None) == ""
