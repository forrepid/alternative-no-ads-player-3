import asyncio
import logging
from typing import Any
from urllib.parse import urljoin

from curl_cffi.requests import AsyncSession

from app.core.bypass.factory import create_bypass_backend
from app.core.config import settings
from app.core.proxy import validate_proxy_url

log = logging.getLogger("http")


class HttpClient:
    """TLS-fingerprint korumali siteler icin chrome impersonation
    kullanan async HTTP istemcisi. Retry + backoff dahili.
    v2: tum istekler secili BypassBackend uzerinden gecer."""

    def __init__(self) -> None:
        self._session: AsyncSession | None = None
        self._bypass = create_bypass_backend(settings)

    @property
    def bypass(self):
        return self._bypass

    async def session(self) -> AsyncSession:
        if self._session is None:
            self._session = AsyncSession(
                impersonate=settings.http_impersonate,
                timeout=settings.http_timeout,
                headers={"Accept-Language": "en-US,en;q=0.9"},
            )
        return self._session

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        resp = await self._request("GET", url, **kwargs)
        return resp.json()

    async def get_text(self, url: str, **kwargs: Any) -> str:
        resp = await self._request("GET", url, **kwargs)
        return resp.text

    async def get_bytes(self, url: str, **kwargs: Any) -> bytes:
        resp = await self._request("GET", url, **kwargs)
        return resp.content

    async def get_proxy_text(self, url: str) -> str:
        return (await self._proxy_request(url)).text

    async def get_proxy_bytes(self, url: str) -> bytes:
        return (await self._proxy_request(url)).content

    async def _proxy_request(self, url: str):
        """Fetch an allowlisted URL while validating every redirect hop."""
        current = url
        for _ in range(4):
            await validate_proxy_url(current)
            response = await self._request("GET", current, allow_redirects=False)
            if response.status_code not in (301, 302, 303, 307, 308):
                return response
            location = response.headers.get("location")
            if not location:
                raise RuntimeError("redirect response has no location")
            current = urljoin(current, location)
        raise RuntimeError("too many HLS redirects")

    async def _request(self, method: str, url: str, **kwargs: Any):
        last_exc: Exception | None = None
        for attempt in range(settings.http_retries):
            try:
                s = await self.session()
                # v2: istek bypass katmanindan gecer
                resp = await self._bypass.request(s, method, url, **kwargs)
                if resp.status_code in (403, 429, 503):
                    log.warning("HTTP %s -> %s (attempt %d)",
                                url, resp.status_code, attempt + 1)
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                resp.raise_for_status()
                return resp
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                log.warning("request error %s (attempt %d): %s",
                            url, attempt + 1, exc)
                await asyncio.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"request failed after retries: {url}") from last_exc

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
        await self._bypass.close()


http = HttpClient()
