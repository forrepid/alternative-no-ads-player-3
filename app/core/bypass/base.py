from abc import ABC, abstractmethod
from typing import Any

from curl_cffi.requests import AsyncSession, Response


class BypassBackend(ABC):
    """Cloudflare bypass backend'i icin ortak arayuz."""

    @abstractmethod
    async def request(
        self,
        session: AsyncSession,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Response:
        """Verilen session uzerinden istegi yapar, Response dondurur."""
        ...

    async def close(self) -> None:
        """Kaynaklari temizle (opsiyonel)."""