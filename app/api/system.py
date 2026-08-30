from aiocache import cached
from fastapi import APIRouter

from app.core.config import settings
from app.core.http import http
from app.main_version import APP_VERSION
from app.providers.twitch_integrity import solver as integrity_solver

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
@cached(ttl=10)
async def health():
    """Aktif modullerin ve alternatif backend'lerin canli durum raporu."""
    s = await http.session()
    bypass_health = await http.bypass.health(s)
    return {
        "version": APP_VERSION,
        "bypass": bypass_health,
        "ad_filter": {
            "enabled": settings.ad_filter_enabled,
            "strategy": settings.ad_filter_strategy,
        },
        "twitch": {
            "stream_source": settings.twitch_stream_source,
            "integrity_mode": settings.twitch_integrity_mode,
            "integrity_solver_available": integrity_solver.available(),
            "helix_configured": bool(settings.twitch_client_id),
        },
        "kick": {
            "official_api_configured": bool(settings.kick_access_token),
        },
        "youtube": {
            "data_api_configured": bool(settings.youtube_api_key),
        },
    }
