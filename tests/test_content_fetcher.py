import ipaddress

import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import AppException
from app.integrations.content.fetcher import UrlFetcher, validate_url
from app.integrations.content.schemas import FetchStatus


def _resolver(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    mapping = {
        "articles.example.com": [ipaddress.ip_address("93.184.216.34")],
        "localhost": [ipaddress.ip_address("127.0.0.1")],
        "blocked.internal": [ipaddress.ip_address("10.0.0.8")],
    }
    if hostname in mapping:
        return mapping[hostname]
    try:
        return [ipaddress.ip_address(hostname)]
    except ValueError as exc:
        raise AppException("FETCH_FAILED", "DNS resolution failed", status_code=502) from exc


def _fetcher(handler) -> UrlFetcher:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, follow_redirects=False)
    return UrlFetcher(client=client, resolver=_resolver)


def test_valid_public_url_mocked_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://articles.example.com/notice"
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><body><p>ok</p></body></html>",
        )

    result = _fetcher(handler).fetch("https://articles.example.com/notice")
    assert result.fetch_status == FetchStatus.SUCCESS
    assert result.status_code == 200
    assert result.content_type == "text/html"


def test_safe_url_rejects_invalid_scheme():
    with pytest.raises(AppException) as exc:
        validate_url("file:///C:/Windows/system.ini", resolver=_resolver)
    assert exc.value.code == "INVALID_URL"


def test_safe_url_rejects_localhost():
    with pytest.raises(AppException) as exc:
        validate_url("http://localhost:8000/docs", resolver=_resolver)
    assert exc.value.code == "UNSAFE_URL"


def test_safe_url_rejects_loopback_ip():
    with pytest.raises(AppException) as exc:
        validate_url("http://127.0.0.1:8000/docs", resolver=_resolver)
    assert exc.value.code == "UNSAFE_URL"


def test_safe_url_rejects_private_ipv4():
    with pytest.raises(AppException) as exc:
        validate_url("http://192.168.1.1", resolver=_resolver)
    assert exc.value.code == "UNSAFE_URL"


def test_safe_url_rejects_private_ipv6():
    with pytest.raises(AppException) as exc:
        validate_url("http://[fd00::1]/", resolver=_resolver)
    assert exc.value.code == "UNSAFE_URL"


def test_redirect_to_private_address_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})
        raise AssertionError("private redirect target must not be requested")

    with pytest.raises(AppException) as exc:
        _fetcher(handler).fetch("https://articles.example.com/start")
    assert exc.value.code == "UNSAFE_URL"


def test_fetch_timeout():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    with pytest.raises(AppException) as exc:
        _fetcher(handler).fetch("https://articles.example.com/slow")
    assert exc.value.code == "FETCH_TIMEOUT"


def test_fetch_404():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="missing")

    with pytest.raises(AppException) as exc:
        _fetcher(handler).fetch("https://articles.example.com/missing")
    assert exc.value.code == "FETCH_FAILED"
    assert exc.value.details["http_status"] == 404


def test_fetch_content_too_large():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-type": "text/html",
                "content-length": str(settings.CONTENT_MAX_BYTES + 1),
            },
            content=b"x",
        )

    with pytest.raises(AppException) as exc:
        _fetcher(handler).fetch("https://articles.example.com/huge")
    assert exc.value.code == "CONTENT_TOO_LARGE"


def test_pdf_is_unsupported_at_fetch_layer():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF-1.4 mock",
        )

    result = _fetcher(handler).fetch("https://articles.example.com/file.pdf")
    assert result.content_type == "application/pdf"
    assert result.fetch_status == FetchStatus.SUCCESS
