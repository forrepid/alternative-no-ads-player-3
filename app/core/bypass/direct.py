import logging
from typing import Any

from curl_cffi.requests import AsyncSession, Response

from app.core.bypass.base import BypassBackend

logger = logging.getLogger(__name__)


class DirectBackend(BypassBackend):
    """Bypass'suz dogrudan baglanti (varsayilan).
    HttpClient'in olusturdugu session'i kullanir."""

    async def request(
        self,
        session: AsyncSession,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Response:
        return await session.request(method, url, **kwargs)

    async def health(self, session: AsyncSession) -> dict:
        """Direct backend her zaman sagliklidir -- dis bagimliligi yok."""
        return {
            "ok": True,
            "mode": "direct",
            "detail": "Direct backend requires no external service",
        }