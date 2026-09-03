"""Tests for safe PJeOffice update discovery."""

from __future__ import annotations

from src.utils import updater


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_update_checker_uses_version_order_not_page_order(monkeypatch) -> None:
    html = b"""
        pjeoffice-pro-v2.5.16u-linux_x64.zip
        pjeoffice-pro-v2.5.14-linux_x64.zip
    """
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *_args, **_kwargs: _Response(html))
    monkeypatch.setattr(updater, "_record_pjeoffice_check", lambda: None)

    result = updater.check_pjeoffice_updates("2.5.15")

    assert result is not None
    assert result.version == "2.5.16u"


def test_update_checker_does_not_offer_downgrade(monkeypatch) -> None:
    html = b"pjeoffice-pro-v2.5.16u-linux_x64.zip"
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *_args, **_kwargs: _Response(html))
    monkeypatch.setattr(updater, "_record_pjeoffice_check", lambda: None)

    assert updater.check_pjeoffice_updates("2.5.17") is None


def test_update_checker_rejects_malformed_checksum(monkeypatch) -> None:
    html = b"""
        pjeoffice-pro-v2.5.17-linux_x64.zip
        pjeoffice-pro-v2.5.17-linux_x64.zip.sha256
    """
    responses = iter([html, b"valor-invalido  arquivo.zip"])
    monkeypatch.setattr(
        updater.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _Response(next(responses)),
    )
    monkeypatch.setattr(updater, "_record_pjeoffice_check", lambda: None)

    result = updater.check_pjeoffice_updates("2.5.16u")

    assert result is not None
    assert result.sha256 == ""
