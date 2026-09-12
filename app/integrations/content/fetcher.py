"""Safe URL validation and HTTP fetch. No content extraction."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import get_logger
from app.integrations.content.schemas import FetchResult, FetchStatus

logger = get_logger(__name__)

Resolver = Callable[[str], list[ipaddress.IPv4Address | ipaddress.IPv6Address]]

_ALLOWED_SCHEMES = {"http", "https"}
_REDIRECT_STATUS = {301, 302, 303, 307, 308}


def resolve_host(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise AppException(
            "FETCH_FAILED",
            "DNS resolution failed",
            status_code=502,
            details={"host": hostname, "reason": str(exc)},
        ) from exc

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        raw_ip = sockaddr[0]
        if raw_ip in seen:
            continue
        seen.add(raw_ip)
        addresses.append(ipaddress.ip_address(raw_ip))
    if not addresses:
        raise AppException(
            "FETCH_FAILED",
            "DNS resolution returned no addresses",
            status_code=502,
            details={"host": hostname},
        )
    return addresses


def _is_unsafe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
        or not ip.is_global
    )


def validate_url(
    url: str,
    *,
    resolver: Resolver = resolve_host,
) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise AppException(
            "INVALID_URL",
            "Only http and https URLs are allowed",
            status_code=400,
            details={"scheme": parsed.scheme or None},
        )
    if parsed.username or parsed.password:
        raise AppException(
            "INVALID_URL",
            "URLs with userinfo are not allowed",
            status_code=400,
        )
    hostname = parsed.hostname
    if not hostname:
        raise AppException(
            "INVALID_URL",
            "URL host is missing",
            status_code=400,
        )

    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        addresses = [literal_ip]
    else:
        addresses = resolver(hostname)

    unsafe = [str(ip) for ip in addresses if _is_unsafe_ip(ip)]
    if unsafe:
        raise AppException(
            "UNSAFE_URL",
            "URL resolves to a blocked address",
            status_code=400,
            details={"host": hostname, "addresses": unsafe},
        )
    return url


def sniff_content_type(content_type: str | None, body: bytes) -> str | None:
    if content_type:
        return content_type.split(";")[0].strip().lower() or None
    sample = body[:1024]
    if sample.startswith(b"%PDF"):
        return "application/pdf"
    lowered = sample.lower()
    if lowered.lstrip().startswith(b"<") or b"<html" in lowered:
        return "text/html"
    return "text/plain"


class UrlFetcher:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        self._external_client = client
        self._resolver = resolver or resolve_host

    def fetch(self, url: str) -> FetchResult:
        current = url.strip()
        hops = 0
        client = self._external_client or httpx.Client(
            timeout=httpx.Timeout(settings.CONTENT_FETCH_TIMEOUT_SECONDS),
            follow_redirects=False,
            headers={"User-Agent": settings.CONTENT_USER_AGENT},
        )
        owns_client = self._external_client is None
        try:
            while True:
                validate_url(current, resolver=self._resolver)
                try:
                    with client.stream("GET", current) as response:
                        if response.status_code in _REDIRECT_STATUS:
                            hops += 1
                            if hops > settings.CONTENT_MAX_REDIRECTS:
                                raise AppException(
                                    "FETCH_FAILED",
                                    "Too many redirects",
                                    status_code=502,
                                )
                            location = response.headers.get("location")
                            if not location:
                                raise AppException(
                                    "FETCH_FAILED",
                                    "Redirect is missing Location",
                                    status_code=502,
                                )
                            current = urljoin(str(response.url), location)
                            continue

                        body = self._read_limited_body(response)
                        content_type = sniff_content_type(
                            response.headers.get("content-type"),
                            body,
                        )
                        host = urlparse(str(response.url)).hostname
                        logger.info(
                            "Fetched host=%s status=%s bytes=%s content_type=%s",
                            host,
                            response.status_code,
                            len(body),
                            content_type,
                        )
                        if response.status_code >= 400:
                            raise AppException(
                                "FETCH_FAILED",
                                "Remote server returned an error",
                                status_code=502,
                                details={"http_status": response.status_code},
                            )
                        return FetchResult(
                            source_url=url,
                            resolved_url=str(response.url),
                            status_code=response.status_code,
                            content_type=content_type,
                            body=body,
                            fetch_status=FetchStatus.SUCCESS,
                        )
                except AppException:
                    raise
                except httpx.TimeoutException as exc:
                    raise AppException(
                        "FETCH_TIMEOUT",
                        "Timed out while fetching URL",
                        status_code=504,
                    ) from exc
                except httpx.TooManyRedirects as exc:
                    raise AppException(
                        "FETCH_FAILED",
                        "Too many redirects",
                        status_code=502,
                    ) from exc
                except httpx.RequestError as exc:
                    raise AppException(
                        "FETCH_FAILED",
                        "Failed to fetch URL",
                        status_code=502,
                        details={"reason": exc.__class__.__name__},
                    ) from exc
        finally:
            if owns_client:
                client.close()

    def _read_limited_body(self, response: httpx.Response) -> bytes:
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                declared = int(content_length)
            except ValueError:
                declared = 0
            if declared > settings.CONTENT_MAX_BYTES:
                raise AppException(
                    "CONTENT_TOO_LARGE",
                    "Remote content exceeds size limit",
                    status_code=413,
                    details={"limit_bytes": settings.CONTENT_MAX_BYTES},
                )

        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > settings.CONTENT_MAX_BYTES:
                raise AppException(
                    "CONTENT_TOO_LARGE",
                    "Remote content exceeds size limit",
                    status_code=413,
                    details={"limit_bytes": settings.CONTENT_MAX_BYTES},
                )
            chunks.append(chunk)
        return b"".join(chunks)
