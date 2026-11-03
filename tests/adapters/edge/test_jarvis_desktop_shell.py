from __future__ import annotations

import pytest

from app.adapters.edge.jarvis_desktop_shell import build_start_url, normalize_cloud_url


def test_default_cloud_origin_is_normalized():
    assert normalize_cloud_url("https://jarvis.example/") == "https://jarvis.example"


@pytest.mark.parametrize(
    ("base_url", "page", "expected"),
    [
        ("https://jarvis.example", "home", "https://jarvis.example/"),
        ("https://jarvis.example/", "intelligence", "https://jarvis.example/intelligence"),
        ("https://jarvis.example/base", "network", "https://jarvis.example/base/network-devices"),
        ("http://127.0.0.1:10000", "home", "http://127.0.0.1:10000/"),
    ],
)
def test_build_start_url(base_url, page, expected):
    assert build_start_url(base_url, page) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "javascript:alert(1)",
        "http://jarvis.example",
        "https://user:password@jarvis.example",
        "https://jarvis.example?token=secret",
        "https://jarvis.example/#fragment",
        "https:///missing-host",
    ],
)
def test_rejects_unsafe_or_invalid_origins(value):
    with pytest.raises(ValueError):
        normalize_cloud_url(value)


def test_rejects_unknown_page():
    with pytest.raises(ValueError):
        build_start_url("https://jarvis.example", "admin")
