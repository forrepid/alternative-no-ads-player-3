import logging
import re

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response

from app.core.config import settings
from app.core.http import http
from app.core.models import ChannelStatus, Platform, StreamInfo
from app.core.proxy import validate_proxy_url
from app.hls.filter import rewrite_master_playlist
from app.hls.strategies import apply_strategy
from app.providers import get_provider

log = logging.getLogger("api")
router = APIRouter(prefix="/api")


def _valid_channel(channel: str) -> str:
    if not re.fullmatch(r"@?[A-Za-z0-9_.-]{2,100}", channel):
        raise HTTPException(400, detail="invalid channel identifier")
    return channel


@router.get("/status/{platform}/{channel}", response_model=ChannelStatus)
async def status(platform: Platform, channel: str):
    return await get_provider(platform).get_status(_valid_channel(channel))


@router.get("/status", response_model=list[ChannelStatus])
async def status_all(channel: str = Query(...)):
    import asyncio
    channel = _valid_channel(channel)
    results = await asyncio.gather(*[
        get_provider(p).get_status(channel) for p in Platform
    ], return_exceptions=True)
    return [result if isinstance(result, ChannelStatus) else ChannelStatus(
        platform=platform, channel=channel, is_live=False, error=str(result))
        for platform, result in zip(Platform, results, strict=False)]


@router.get("/stream/{platform}/{channel}", response_model=StreamInfo)
async def stream(platform: Platform, channel: str):
    info = await get_provider(platform).get_stream(_valid_channel(channel))
    if not info.is_live:
        raise HTTPException(404, detail="channel offline or stream unavailable")
    return info


@router.get("/hls/master", response_class=PlainTextResponse)
async def hls_master(url: str = Query(...)):
    url = await validate_proxy_url(url)
    body = await http.get_proxy_text(url)
    rewritten = rewrite_master_playlist(body, url, "/api/hls/media")
    return PlainTextResponse(rewritten,
                             media_type="application/vnd.apple.mpegurl")


@router.get("/hls/media", response_class=PlainTextResponse)
async def hls_media(url: str = Query(...),
                    strategy: str | None = Query(None)):
    """Media playlist'i cekip secili stratejiyle reklamlari filtreler.
    v2: ?strategy=none|scte35|aggressive ile istek bazinda secim."""
    url = await validate_proxy_url(url)
    body = await http.get_proxy_text(url)
    chosen = strategy or (
        settings.ad_filter_strategy if settings.ad_filter_enabled else "none")
    filtered, removed = apply_strategy(chosen, body, url)
    if removed:
        log.info("ad-filter[%s]: %d segment removed from %s",
                 chosen, removed, url[:80])
    return PlainTextResponse(filtered,
                             media_type="application/vnd.apple.mpegurl")


@router.get("/hls/segment")
async def hls_segment(url: str = Query(...)):
    url = await validate_proxy_url(url)
    data = await http.get_proxy_bytes(url)
    return Response(content=data, media_type="application/octet-stream",
                    headers={"Cache-Control": "no-store"})
