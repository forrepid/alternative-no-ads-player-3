import logging
import time
from typing import Any
from urllib.parse import urlparse

from curl_cffi.requests import AsyncSession

from app.core.bypass.base import BypassBackend

log = logging.getLogger("bypass.cf_server")


class CloudflareServerBackend(BypassBackend):
    """ghcr.io/sarperavci/cloudflarebypassforscraping sunucusu entegrasyonu.

    Iki mod:
      mirror  -> istek bypass sunucusuna 'x-hostname' header'i ile aynen
                 iletilir; sunucu gercek siteye replay eder. (en saglam)
      cookies -> sunucudan cf_clearance + user-agent alinir, dogrudan
                 istekte kullanilir. (daha hizli, cookie TTL ile cache'lenir)
    """

    name = "cf_server"

    def __init__(self, server_url: str, mode: str = "mirror",
                 cookie_ttl: int = 1800,
                 protected_hosts: tuple[str, ...] = ("kick.com",)) -> None:
        self.server_url = server_url.rstrip("/")
        self.mode = mode
        self.cookie_ttl = cookie_ttl
        self.protected_hosts = protected_hosts
        # host -> (cf_clearance, user_agent, expire_ts)
        self._cookie_cache: dict[str, tuple[str, str, float]] = {}

    # ---------- yardimcilar ----------
    def _is_protected(self, url: str) -> bool:
        host = urlparse(url).hostname or ""
        return any(host == h or host.endswith("." + h)
                   for h in self.protected_hosts)

    async def _get_clearance(self, session: AsyncSession,
                             host: str) -> tuple[str, str] | None:
        """Bypass sunucusundan cf_clearance cookie + UA cifti alir (cache'li)."""
        cached = self._cookie_cache.get(host)
        if cached and cached[2] > time.time():
            return cached[0], cached[1]
        try:
            resp = await session.get(
                f"{self.server_url}/cookies",
                params={"url": f"https://{host}/"},
                impersonate=None,  # sunucuya giden istekte impersonation gereksiz
            )
            if resp.status_code != 200:
                log.warning("cf cookie endpoint %s -> %s", host, resp.status_code)
                return None
            data = resp.json()
            clearance = (data.get("cookies") or {}).get("cf_clearance")
            ua = data.get("user_agent")
            if not clearance or not ua:
                return None
            self._cookie_cache[host] = (
                clearance, ua, time.time() + self.cookie_ttl)
            log.info("cf_clearance alindi: %s", host)
            return clearance, ua
        except Exception as exc:  # noqa: BLE001
            log.warning("cf cookie alinamadi (%s): %s", host, exc)
            return None

    # ---------- ana istek ----------
    async def request(self, session: AsyncSession, method: str,
                      url: str, **kwargs: Any):
        if not self._is_protected(url):
            return await session.request(method, url, **kwargs)

        if self.mode == "mirror":
            return await self._mirror(session, method, url, **kwargs)
        return await self._with_cookies(session, method, url, **kwargs)

    async def _mirror(self, session: AsyncSession, method: str,
                      url: str, **kwargs: Any):
        """Istegi bypass sunucusu uzerinden gercek hosta replay ettirir."""
        parsed = urlparse(url)
        mirror_url = f"{self.server_url}{parsed.path}"
        if parsed.query:
            mirror_url += f"?{parsed.query}"
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["x-hostname"] = parsed.hostname or ""
        log.debug("mirror -> %s via %s", url, self.server_url)
        return await session.request(method, mirror_url,
                                     headers=headers, **kwargs)

    async def _with_cookies(self, session: AsyncSession, method: str,
                            url: str, **kwargs: Any):
        """cf_clearance cookie'sini dogrudan istege enjekte eder."""
        host = urlparse(url).hostname or ""
        pair = await self._get_clearance(session, host)
        if pair:
            clearance, ua = pair
            headers = dict(kwargs.pop("headers", {}) or {})
            headers["User-Agent"] = ua  # cookie ile eslesen UA zorunlu
            cookies = dict(kwargs.pop("cookies", {}) or {})
            cookies["cf_clearance"] = clearance
            kwargs["headers"] = headers
            kwargs["cookies"] = cookies
        return await session.request(method, url, **kwargs)

    # ---------- saglik ----------
    async def health(self, session: AsyncSession) -> dict:
        try:
            resp = await session.get(f"{self.server_url}/cookies",
                                     params={"url": "https://kick.com/"},
                                     timeout=10)
            ok = resp.status_code == 200
        except Exception as exc:  # noqa: BLE001
            return {"backend": self.name, "mode": self.mode,
                    "reachable": False, "error": str(exc)}
        return {"backend": self.name, "mode": self.mode, "reachable": ok,
                "cached_cookies": list(self._cookie_cache)}

    async def close(self) -> None:
        self._cookie_cache.clear()