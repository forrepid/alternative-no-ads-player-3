"""HLS proxy URL validation and query construction helpers."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlencode, urlparse

from fastapi import HTTPException

from app.core.config import settings

DEFAULT_ALLOWED_SUFFIXES = (
    "ttvnw.net",
    "twitchcdn.net",
    "twitch.tv",
    "kick.com",
    "live-video.net",
    "cloudfront.net",
    "amazonaws.com",
    "googlevideo.com",
    "youtube.com",
    "youtu.be",
    "ttv.lol",
)


def proxy_url(path: str, target: str, **params: str) -> str:
    """Build a local proxy URL without leaking target query parameters."""
    return f"{path}?{urlencode({'url': target, **params})}"


def _allowed_suffixes() -> tuple[str, ...]:
    configured = tuple(
        item.strip().lower().lstrip(".")
        for item in settings.hls_allowed_hosts.split(",")
        if item.strip()
    )
    return configured or DEFAULT_ALLOWED_SUFFIXES


def _is_allowed_host(host: str) -> bool:
    return any(host == suffix or host.endswith(f".{suffix}")
               for suffix in _allowed_suffixes())


async def validate_proxy_url(url: str) -> str:
    """Reject non-HTTPS, untrusted, and non-public HLS destinations."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise HTTPException(400, detail="Only authenticated-free HTTPS URLs are supported")
    if parsed.port not in (None, 443):
        raise HTTPException(400, detail="Only HTTPS port 443 is supported")
    if not _is_allowed_host(host):
        raise HTTPException(403, detail="HLS host is not allowed")

    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, 443, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HTTPException(400, detail="HLS host could not be resolved") from exc
    if not infos:
        raise HTTPException(400, detail="HLS host could not be resolved")
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise HTTPException(403, detail="Private or reserved HLS addresses are blocked")
    return url
