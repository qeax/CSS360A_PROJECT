"""Sanitize listing HTML for safe rendering in the UI."""

from __future__ import annotations

import bleach
from bleach.css_sanitizer import ALLOWED_CSS_PROPERTIES, CSSSanitizer

ALLOWED_TAGS = [
    "p",
    "div",
    "span",
    "br",
    "hr",
    "b",
    "strong",
    "i",
    "em",
    "u",
    "ul",
    "ol",
    "li",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "a",
    "img",
    "font",
    "center",
    "blockquote",
    "pre",
    "sub",
    "sup",
    "style",
]

ALLOWED_ATTRIBUTES = {
    "*": ["class", "style", "id", "align", "width", "height", "colspan", "rowspan"],
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
}

ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

_CSS_SANITIZER = CSSSanitizer(allowed_css_properties=ALLOWED_CSS_PROPERTIES)


def sanitize_listing_html(raw: str | None) -> str:
    """Return HTML safe for innerHTML (strips scripts, event handlers, etc.)."""
    if not raw or not str(raw).strip():
        return ""
    cleaned = bleach.clean(
        str(raw),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
        css_sanitizer=_CSS_SANITIZER,
    )
    return cleaned.strip()
