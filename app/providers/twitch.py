import logging
import time
from urllib.parse import quote

from aiocache import cached

from app.core.config import settings
from app.core.http import http
from app.core.models import ChannelStatus, Platform, StreamInfo
from app.core.proxy import proxy_url
from app.hls.variants import parse_variants
from app.providers.base import BaseProvider
from app.providers.twitch_integrity import solver as integrity_solver

log = logging.getLogger("provider.twitch")

GQL_URL = "https://gql.twitch.tv/gql"
HELIX = "https://api.twitch.tv/helix"
PUBLIC_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"

# PlaybackAccessToken persisted query (v1 ile ayni)
_PAT_HASH = "0828119ded1c13477966434e15800ff57ddacf13ba1911c129dc2200705b0712"


class TwitchProvider(BaseProvider):
    """Twitch wrapper v2:
    - Durum/metadata: Helix (anahtar varsa) veya GQL.        [v1 - korundu]
    - Yayin URL: 2 alternatif kaynak:
        direct   -> GQL PlaybackAccessToken + usher HLS
                    (gerekirse client-integrity cozucu devreye girer)
        ttv_lol  -> TTV-LOL tarzi upstream proxy; reklamsiz playlist
                    dondurur, SCTE-35 filtrelemesine gerek kalmaz.
    """

    name = "twitch"
    _app_token: str | None = None
    _app_token_expires_at: float = 0

    # ---------- resmi Helix (v1 - korundu) ----------
    async def _helix_token(self) -> str | None:
        if not (settings.twitch_client_id and settings.twitch_client_secret):
            return None
        if self._app_token and self._app_token_expires_at > time.monotonic() + 60:
            return self._app_token
        s = await http.session()
        resp = await s.post("https://id.twitch.tv/oauth2/token", params={
            "client_id": settings.twitch_client_id,
            "client_secret": settings.twitch_client_secret,
            "grant_type": "client_credentials",
        })
        if resp.status_code == 200:
            token_data = resp.json()
            self._app_token = token_data["access_token"]
            self._app_token_expires_at = (
                time.monotonic() + int(token_data.get("expires_in", 3600)))
        return self._app_token

    async def _helix_status(self, channel: str) -> ChannelStatus | None:
        token = await self._helix_token()
        if not token:
            return None
        try:
            data = await http.get_json(
                f"{HELIX}/streams?user_login={channel}",
                headers={"Client-ID": settings.twitch_client_id,
                         "Authorization": f"Bearer {token}"},
            )
            streams = data.get("data") or []
            if not streams:
                return ChannelStatus(platform=Platform.twitch,
                                     channel=channel, is_live=False)
            st = streams[0]
            return ChannelStatus(
                platform=Platform.twitch, channel=channel, is_live=True,
                title=st.get("title"), category=st.get("game_name"),
                viewers=st.get("viewer_count"),
                thumbnail=(st.get("thumbnail_url") or "")
                .replace("{width}", "640").replace("{height}", "360"),
                started_at=st.get("started_at"),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("helix failed: %s", exc)
            return None

    # ---------- GQL (v2: opsiyonel Client-Integrity header'i) ----------
    async def _gql(self, payload: dict | list,
                   integrity_token: str | None = None) -> dict | list:
        s = await http.session()
        headers = {
            "Client-ID": PUBLIC_CLIENT_ID,
            "Content-Type": "application/json",
        }
        if integrity_token:
            headers["Client-Integrity"] = integrity_token
            headers["X-Device-Id"] = "streambridge"
        resp = await s.post(GQL_URL, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

    # ---------- durum (v1 - korundu) ----------
    @cached(ttl=settings.cache_ttl_status)
    async def get_status(self, channel: str) -> ChannelStatus:
        status = await self._helix_status(channel)
        if status:
            return status
        try:
            data = await self._gql({
                "operationName": "ChannelShell",
                "variables": {"login": channel},
                "query": """query ChannelShell($login: String!) {
                    user(login: $login) {
                        displayName
                        stream {
                            title type viewersCount createdAt
                            game { name }
                            previewImageURL(width: 640, height: 360)
                        }
                    }
                }""",
            })
            user = (data.get("data") or {}).get("user") or {}
            st = user.get("stream")
            if not st or st.get("type") != "live":
                return ChannelStatus(platform=Platform.twitch,
                                     channel=channel, is_live=False)
            return ChannelStatus(
                platform=Platform.twitch, channel=channel, is_live=True,
                title=st.get("title"),
                category=(st.get("game") or {}).get("name"),
                viewers=st.get("viewersCount"),
                thumbnail=st.get("previewImageURL"),
                started_at=st.get("createdAt"),
            )
        except Exception as exc:  # noqa: BLE001
            return ChannelStatus(platform=Platform.twitch, channel=channel,
                                 is_live=False, error=str(exc))

    # ---------- yayin (v2: kaynak secimi) ----------
    async def get_stream(self, channel: str) -> StreamInfo:
        info: StreamInfo
        if settings.twitch_stream_source == "ttv_lol":
            info = await self._stream_via_ttv_lol(channel)
            if info.is_live:
                return await self._attach_status(info)
            log.info("ttv_lol basarisiz, direct'e dusuluyor: %s", channel)
        info = await self._stream_direct(channel)
        return await self._attach_status(info)

    async def _attach_status(self, info: StreamInfo) -> StreamInfo:
        """Oynatici overlay'i icin platform metadata'sini stream yanitina ekler."""
        if not info.is_live:
            return info
        status = await self.get_status(info.channel)
        info.title = info.title or status.title
        info.viewers = status.viewers
        info.category = status.category
        info.started_at = status.started_at
        return info

    async def _stream_via_ttv_lol(self, channel: str) -> StreamInfo:
        """TTV-LOL tarzi upstream proxy: usher istegini proxy uzerinden
        yapar; donen playlist reklamsizdur. SCTE-35 filtresi yedekte kalir."""
        info = StreamInfo(platform=Platform.twitch, channel=channel,
                          is_live=False, source="ttv_lol")
        try:
            url = (f"{settings.ttv_lol_proxy}/playlist/{channel}.m3u8"
                   f"?allow_source=true&allow_audio_only=true&fast_bread=true"
                   f"&supported_codecs=h264")
            body = await http.get_text(url)
            if "#EXTM3U" not in body or "#EXT-X-STREAM-INF" not in body:
                return info
            info.is_live = True
            # BUGFIX(v2): & iceren URL'ler query'yi bozmasin diye encode
            info.master_playlist = proxy_url("/api/hls/master", url)
            info.variants = parse_variants(body, url)
            info.ads_filtered = True  # upstream reklamlari zaten ayiklar
            return info
        except Exception as exc:  # noqa: BLE001
            info.error = str(exc)
            return info

    async def _stream_direct(self, channel: str) -> StreamInfo:
        """v1 akisi + client-integrity fallback zinciri."""
        info = StreamInfo(platform=Platform.twitch, channel=channel,
                          is_live=False, source="direct")
        token_data = await self._playback_access_token(channel)
        if not token_data:
            info.error = "playback access token alinamadi"
            return info
        # GQL, value alanini zaten JSON metni olarak dondurur. Yeniden
        # json.dumps yapmak token'i JSON-string'e cevirir ("{\\\"...}") ve
        # Usher bunu nauth token olarak okuyamaz; sonucu 403 olur.
        token = quote(token_data["value"], safe="")
        sig = token_data["signature"]
        usher = (
            f"https://usher.ttvnw.net/api/channel/hls/{channel}.m3u8"
            f"?sig={sig}&token={token}"
            "&allow_source=true&allow_audio_only=true&fast_bread=true"
            "&player_backend=mediaplayer&playlist_include_framerate=true"
            "&supported_codecs=h264"
        )
        try:
            playlist = await http.get_text(usher)
            if "#EXTM3U" not in playlist:
                info.error = "Twitch geçerli bir HLS oynatma listesi döndürmedi"
                return info
            info.variants = parse_variants(playlist, usher)
        except Exception as exc:  # noqa: BLE001
            # Geçersiz bir master URL'yi istemciye vermek yerine anlaşılır bir
            # hata döndürürüz. Böylece player sonsuz yükleme durumunda kalmaz.
            log.warning("twitch master unavailable for %s: %s", channel, exc)
            info.error = "Twitch HLS listesine erişilemedi"
            return info
        info.is_live = True
        info.master_playlist = proxy_url("/api/hls/master", usher)
        # HLS CDN veya filtreleme katmanı erişilemezse, Twitch'in desteklediği
        # resmi gömülü oynatıcı yayın erişimini korur. parent değeri istemcide
        # bulunduğu origin'e göre güncellenir.
        info.fallback_embed_url = (
            f"https://player.twitch.tv/?channel={channel}&parent=localhost"
            "&autoplay=true&muted=true"
        )
        info.ads_filtered = settings.ad_filter_enabled
        return info

    async def _playback_access_token(self, channel: str) -> dict | None:
        """GQL'den token alir; CI gerekirse solver ile tekrar dener."""
        payload = {
            "operationName": "PlaybackAccessToken",
            "variables": {
                "isLive": True, "login": channel, "isVod": False,
                "vodID": "", "playerType": "site",
            },
            "extensions": {"persistedQuery": {"version": 1,
                                              "sha256Hash": _PAT_HASH}},
        }
        # 1. deneme: integrity'siz (v1 davranisi)
        try:
            data = await self._gql(payload)
            token_data = (data.get("data") or {}).get(
                "streamPlaybackAccessToken")
            if token_data:
                return token_data
            # GQL hata dondurduyse CI gerekiyor olabilir
            errors = data.get("errors") or []
            needs_ci = any("integrity" in (e.get("message") or "").lower()
                           for e in errors)
            if not needs_ci and settings.twitch_integrity_mode != "force":
                return None
        except Exception as exc:  # noqa: BLE001
            log.info("GQL ilk deneme hatasi: %s", exc)
            if settings.twitch_integrity_mode == "off":
                return None

        # 2. deneme: client-integrity token ile
        ci = await integrity_solver.get_token()
        if not ci:
            log.warning("client-integrity token alinamadi")
            return None
        try:
            data = await self._gql(payload, integrity_token=ci)
            token_data = (data.get("data") or {}).get(
                "streamPlaybackAccessToken")
            if token_data:
                return token_data
            # token bayat olabilir: zorla yenile, son bir deneme
            ci = await integrity_solver.get_token(force_refresh=True)
            if ci:
                data = await self._gql(payload, integrity_token=ci)
                return (data.get("data") or {}).get(
                    "streamPlaybackAccessToken")
        except Exception as exc:  # noqa: BLE001
            log.warning("GQL integrity denemesi hatasi: %s", exc)
        return None
