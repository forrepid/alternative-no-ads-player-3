import logging

from aiocache import cached

from app.core.config import settings
from app.core.http import http
from app.core.models import ChannelStatus, Platform, StreamInfo, StreamVariant
from app.core.proxy import proxy_url
from app.providers.base import BaseProvider

log = logging.getLogger("provider.kick")

WEB_BASE = "https://kick.com"
PUBLIC_API = "https://api.kick.com/public/v1"


class KickProvider(BaseProvider):
    """Kick wrapper: resmi public API (token varsa) + web API v1/v2 fallback.
    Kick canli yayinlari AWS IVS HLS uzerinden sunar; playback_url dogrudan
    oynatilabilir ve sunucu tarafli reklam icermez."""

    name = "kick"

    # ---------- resmi public API (opsiyonel) ----------
    async def _official_channels(self, slug: str) -> dict | None:
        if not settings.kick_access_token:
            return None
        try:
            data = await http.get_json(
                f"{PUBLIC_API}/channels?slug={slug}",
                headers={"Authorization": f"Bearer {settings.kick_access_token}"},
            )
            items = data.get("data") or []
            return items[0] if items else None
        except Exception as exc:  # noqa: BLE001
            log.warning("kick official api failed: %s", exc)
            return None

    # ---------- web API v2 -> v1 fallback ----------
    async def _web_channel(self, slug: str) -> dict:
        for version in ("v2", "v1"):
            try:
                return await http.get_json(
                    f"{WEB_BASE}/api/{version}/channels/{slug}",
                    headers={"Referer": f"{WEB_BASE}/{slug}"},
                )
            except Exception as exc:  # noqa: BLE001
                log.info("kick api/%s failed for %s: %s", version, slug, exc)
        raise RuntimeError(f"kick channel not reachable: {slug}")

    @cached(ttl=settings.cache_ttl_status)
    async def get_status(self, channel: str) -> ChannelStatus:
        try:
            data = await self._web_channel(channel)
            ls = data.get("livestream")
            is_live = bool(ls and ls.get("is_live"))
            return ChannelStatus(
                platform=Platform.kick,
                channel=channel,
                is_live=is_live,
                title=(ls or {}).get("session_title"),
                category=((ls or {}).get("categories") or [{}])[0].get("name"),
                viewers=(ls or {}).get("viewer_count"),
                thumbnail=((ls or {}).get("thumbnail") or {}).get("url")
                          if isinstance((ls or {}).get("thumbnail"), dict)
                          else (ls or {}).get("thumbnail"),
                started_at=(ls or {}).get("created_at"),
            )
        except Exception as exc:  # noqa: BLE001
            return ChannelStatus(platform=Platform.kick, channel=channel,
                                 is_live=False, error=str(exc))

    async def get_stream(self, channel: str) -> StreamInfo:
        data = await self._web_channel(channel)
        ls = data.get("livestream") or {}
        playback = data.get("playback_url") or ls.get("playback_url")
        is_live = bool(ls.get("is_live")) and bool(playback)
        info = StreamInfo(
            platform=Platform.kick,
            channel=channel,
            is_live=is_live,
            title=ls.get("session_title"),
        )
        if not is_live:
            return info

        # master playlist'i cek, variant'lari listele
        body = await http.get_text(playback)
        info.master_playlist = proxy_url("/api/hls/master", playback)
        info.variants = _parse_variants(body, playback)
        return info


def _parse_variants(master_body: str, base_url: str) -> list[StreamVariant]:
    variants: list[StreamVariant] = []
    pending: dict = {}
    from urllib.parse import urljoin
    for line in master_body.splitlines():
        s = line.strip()
        if s.startswith("#EXT-X-STREAM-INF"):
            attrs = {}
            for part in s.split(":", 1)[1].split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    attrs[k.strip()] = v.strip().strip('"')
            pending = attrs
        elif s and not s.startswith("#") and pending:
            variants.append(StreamVariant(
                quality=pending.get("NAME") or pending.get("RESOLUTION", "?"),
                url=urljoin(base_url, s),
                resolution=pending.get("RESOLUTION"),
                bandwidth=int(pending["BANDWIDTH"]) if pending.get("BANDWIDTH", "").isdigit() else None,
            ))
            pending = {}
    return variants
