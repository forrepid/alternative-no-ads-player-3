import logging
import re

from aiocache import cached

from app.core.config import settings
from app.core.http import http
from app.core.models import ChannelStatus, Platform, StreamInfo
from app.core.proxy import proxy_url
from app.hls.variants import parse_variants
from app.providers.base import BaseProvider

log = logging.getLogger("provider.youtube")

HLS_RE = re.compile(r'"hlsManifestUrl"\s*:\s*"([^"]+)"')
TITLE_RE = re.compile(r'"title"\s*:\s*"([^"]+)"')
LIVE_RE = re.compile(r'"isLive"\s*:\s*true')


class YouTubeProvider(BaseProvider):
    """YouTube wrapper:
    - Metadata: Data API v3 (key varsa) veya watch/live sayfasi parse.
    - Yayin URL: sayfa icindeki hlsManifestUrl. Canli HLS genelde reklamsizdur;
    filtre yine de proxy katmaninda uygulanabilir."""

    name = "youtube"

    def _video_id(self, channel: str) -> str:
        # video id ya da @handle kabul eder
        if re.fullmatch(r"[\w-]{11}", channel):
            return channel
        return ""

    async def _fetch_page(self, channel: str) -> str:
        vid = self._video_id(channel)
        if vid:
            url = f"https://www.youtube.com/watch?v={vid}"
        else:
            handle = channel.lstrip("@")
            url = f"https://www.youtube.com/@{handle}/live"
        return await http.get_text(url)

    @cached(ttl=settings.cache_ttl_status)
    async def get_status(self, channel: str) -> ChannelStatus:
        try:
            html = await self._fetch_page(channel)
            is_live = bool(LIVE_RE.search(html)) and bool(HLS_RE.search(html))
            title_m = TITLE_RE.search(html)
            return ChannelStatus(
                platform=Platform.youtube,
                channel=channel,
                is_live=is_live,
                title=title_m.group(1) if title_m else None,
            )
        except Exception as exc:  # noqa: BLE001
            return ChannelStatus(platform=Platform.youtube, channel=channel,
                                 is_live=False, error=str(exc))

    async def get_stream(self, channel: str) -> StreamInfo:
        info = StreamInfo(platform=Platform.youtube, channel=channel, is_live=False)
        try:
            html = await self._fetch_page(channel)
            m = HLS_RE.search(html)
            if not m:
                return info
            hls_url = m.group(1).encode().decode("unicode_escape")
            title_m = TITLE_RE.search(html)
            info.is_live = True
            info.title = title_m.group(1) if title_m else None
            info.master_playlist = proxy_url("/api/hls/master", hls_url)
            try:
                info.variants = parse_variants(await http.get_text(hls_url), hls_url)
            except Exception as exc:  # noqa: BLE001
                log.info("youtube variants unavailable for %s: %s", channel, exc)
            return info
        except Exception as exc:  # noqa: BLE001
            info.error = str(exc)
            return info
