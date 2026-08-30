import logging
import re
from typing import Callable

from app.hls.filter import filter_media_playlist

log = logging.getLogger("hls.strategies")

# aggressive modda ek olarak yakalanan pattern'ler
AGGRESSIVE_EXTRA = [
    re.compile(r"#EXT-X-DISCONTINUITY-SEQUENCE", re.I),  # gecis korunur ama isaretlenir
    re.compile(r"X-PLAYOUT-LIMIT", re.I),
    re.compile(r"preroll|midroll|commercial", re.I),
]


def strategy_none(body: str, base_url: str) -> tuple[str, int]:
    """Filtreleme yapma; tum medya URI'lerini guvenli proxy'ye yonlendir."""
    from urllib.parse import urljoin

    from app.core.proxy import proxy_url
    from app.hls.filter import _rewrite_uri_attributes
    out = []
    for line in body.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            line = proxy_url("/api/hls/segment", urljoin(base_url, s))
        elif 'URI="' in s:
            line = _rewrite_uri_attributes(line, base_url)
        out.append(line)
    return "\n".join(out) + "\n", 0


def strategy_scte35(body: str, base_url: str) -> tuple[str, int]:
    """v1'deki kanitlanmis SCTE-35 / stitched-ad filtresi."""
    return filter_media_playlist(body, base_url)


def strategy_aggressive(body: str, base_url: str) -> tuple[str, int]:
    """scte35 + ek pattern'ler. Yanlis-pozitif riski daha yuksek;
    twitch manifesti reklam etiketlerini degistirdiginde gecici cozum."""
    filtered, removed = strategy_scte35(body, base_url)
    lines = filtered.splitlines()
    out: list[str] = []
    extra_removed = 0
    skip_uri = False
    for line in lines:
        s = line.strip()
        if any(p.search(s) for p in AGGRESSIVE_EXTRA):
            skip_uri = True
            continue
        if skip_uri and s and not s.startswith("#"):
            extra_removed += 1
            skip_uri = False
            continue
        if not s.startswith("#"):
            skip_uri = False
        out.append(line)
    return "\n".join(out) + "\n", removed + extra_removed


STRATEGIES: dict[str, Callable[[str, str], tuple[str, int]]] = {
    "none": strategy_none,
    "scte35": strategy_scte35,
    "aggressive": strategy_aggressive,
}


def apply_strategy(name: str, body: str, base_url: str) -> tuple[str, int]:
    fn = STRATEGIES.get(name, strategy_scte35)
    return fn(body, base_url)
