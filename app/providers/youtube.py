import json
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

HLS_RE = re.compile(r'"hlsManifestUrl"\s*:\s*"((?:\\.|[^"\\])*)"')
TITLE_RE = re.compile(r'"title"\s*:\s*"([^"]+)"')
LIVE_RE = re.compile(r'"(?:isLive|isLiveContent)"\s*:\s*true')
CHANNEL_ID_RE = re.compile(r"UC[\w-]{22}$")


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
        elif CHANNEL_ID_RE.fullmatch(channel):
            # UC... bir kanal kimliğidir; @handle değildir. @UC.../live
            # isteği HTML döndürse bile canlı akış bilgisini içermez.
            url = f"https://www.youtube.com/channel/{channel}/live"
        else:
            handle = channel.lstrip("@")
            url = f"https://www.youtube.com/@{handle}/live"
        return await http.get_text(url)

    @cached(ttl=settings.cache_ttl_status)
    async def get_status(self, channel: str) -> ChannelStatus:
        try:
            html = await self._fetch_page(channel)
            is_live = bool(HLS_RE.search(html)) and bool(LIVE_RE.search(html))
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
            # YouTube player response içindeki URL JSON-string olarak escape
            # edilir (\\/ ve \\u0026 dahil). json.loads bunları doğru çözer.
            hls_url = json.loads(f'"{m.group(1)}"')
            title_m = TITLE_RE.search(html)
            playlist = await http.get_text(hls_url)
            if "#EXTM3U" not in playlist:
                info.error = "YouTube geçerli bir HLS oynatma listesi döndürmedi"
                return info
            info.is_live = True
            info.title = title_m.group(1) if title_m else None
            info.master_playlist = proxy_url("/api/hls/master", hls_url)
            info.variants = parse_variants(playlist, hls_url)
            return info
        except Exception as exc:  # noqa: BLE001
            info.error = str(exc)
            return info
