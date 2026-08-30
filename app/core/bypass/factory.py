import logging

from app.core.bypass.base import BypassBackend
from app.core.bypass.direct import DirectBackend

log = logging.getLogger("bypass.factory")


def create_bypass_backend(settings) -> BypassBackend:
    """BYPASS_BACKEND env degiskenine gore backend uretir.

    direct    -> varsayilan, curl_cffi impersonation (v1 davranisi)
    cf_server -> CloudflareBypassForScraping sunucusu (mirror/cookies)
    """
    kind = (settings.bypass_backend or "direct").lower()
    if kind == "cf_server":
        from app.core.bypass.cf_server import CloudflareServerBackend
        log.info("bypass backend: cf_server (%s, mode=%s)",
                 settings.cf_bypass_url, settings.cf_bypass_mode)
        return CloudflareServerBackend(
            server_url=settings.cf_bypass_url,
            mode=settings.cf_bypass_mode,
            cookie_ttl=settings.cf_cookie_ttl,
            protected_hosts=tuple(
                h.strip() for h in settings.cf_protected_hosts.split(",")
                if h.strip()),
        )
    log.info("bypass backend: direct")
    return DirectBackend()