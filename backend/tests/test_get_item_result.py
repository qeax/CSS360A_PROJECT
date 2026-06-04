"""Tests for eBay getItem result classification."""

from __future__ import annotations

from app.integrations.ebay.client import GetItemResult


def test_get_item_result_ok():
    detail = {"itemId": "v1|1|0", "title": "Test"}
    result = GetItemResult.ok(detail)
    assert result.status == "ok"
    assert result.detail == detail


def test_get_item_result_not_found():
    result = GetItemResult.not_found(404)
    assert result.status == "not_found"
    assert result.http_status == 404


def test_get_item_result_error():
    result = GetItemResult.error(503)
    assert result.status == "error"
    assert result.http_status == 503
