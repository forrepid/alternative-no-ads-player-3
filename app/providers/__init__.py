from typing import Dict, Type

from app.providers.base import BaseProvider
from app.providers.kick import KickProvider
from app.providers.twitch import TwitchProvider
from app.providers.youtube import YouTubeProvider

_PROVIDERS: Dict[str, Type[BaseProvider]] = {
    "kick": KickProvider,
    "twitch": TwitchProvider,
    "youtube": YouTubeProvider,
}

_instances: Dict[str, BaseProvider] = {}


def get_provider(name: str) -> BaseProvider:
    """Platform adina gore provider ornegi dondurur (tekil)."""
    key = name.lower().strip()
    if key not in _PROVIDERS:
        raise ValueError(f"Bilinmeyen platform: {name}")
    if key not in _instances:
        _instances[key] = _PROVIDERS[key]()
    return _instances[key]


def list_platforms() -> list[str]:
    return sorted(_PROVIDERS.keys())