import re
from urllib.parse import urljoin

from app.core.proxy import proxy_url

# Twitch SSAI (SureStream) ve genel SCTE-35 reklam isaretleri
AD_PATTERNS = [
    re.compile(r'CLASS="twitch-stitched-ad"', re.I),
    re.compile(r'ID="stitched-ad-', re.I),
    re.compile(r"X-TV-TWITCH-AD-", re.I),
    re.compile(r'X-ASSET.*amazon-adsystem', re.I),
    re.compile(r"#EXT-X-DATERANGE.*\bAD\b", re.I),
    re.compile(r"#EXT-X-SCTE35", re.I),
    re.compile(r"#EXT-X-CUE-OUT", re.I),
]

CUE_IN = re.compile(r"#EXT-X-CUE-IN")


def is_ad_line(line: str) -> bool:
    return any(p.search(line) for p in AD_PATTERNS)


def _rewrite_uri_attributes(line: str, base_url: str) -> str:
    def repl(match: re.Match) -> str:
        absolute = urljoin(base_url, match.group(1))
        return f'URI="{proxy_url("/api/hls/segment", absolute)}"'
    return re.sub(r'URI="([^"]+)"', repl, line)


def filter_media_playlist(body: str, base_url: str) -> tuple[str, int]:
    """Media playlist'ten reklam segmentlerini cikarir.
    Dondurur: (temiz playlist, kaldirilan segment sayisi)"""
    lines = body.splitlines()
    out: list[str] = []
    removed = 0
    in_ad = False          # CUE-OUT .. CUE-IN arasi
    skip_next_uri = False  # daterange isaretinden sonraki segment

    for line in lines:
        stripped = line.strip()

        if in_ad:
            if CUE_IN.search(stripped):
                in_ad = False
            if stripped and not stripped.startswith("#"):
                removed += 1
            continue

        if re.search(r"#EXT-X-CUE-OUT", stripped):
            in_ad = True
            removed += 1
            continue

        if is_ad_line(stripped):
            skip_next_uri = True
            continue

        if skip_next_uri:
            # reklam isaretine bagli segment/discontinuity satirlarini atla
            if stripped.startswith("#EXT-X-DISCONTINUITY"):
                continue
            if stripped and not stripped.startswith("#"):
                removed += 1
                skip_next_uri = False
                continue
            if stripped.startswith(("#EXTINF", "#EXT-X-BYTERANGE", "#EXT-X-MAP")):
                continue
            # Segment metadata may span multiple tag lines. Keep waiting for URI.
            continue

        # goreli URI'leri mutlak yap (player segmentleri proxy uzerinden istesin)
        if stripped and not stripped.startswith("#"):
            line = proxy_url("/api/hls/segment", urljoin(base_url, stripped))
        elif 'URI="' in stripped:
            line = _rewrite_uri_attributes(line, base_url)

        out.append(line)

    return "\n".join(out) + "\n", removed


def rewrite_master_playlist(body: str, base_url: str, proxy_prefix: str) -> str:
    """Master playlist'teki variant URI'lerini proxy uzerinden yonlendirir."""
    out: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            absolute = urljoin(base_url, stripped)
            out.append(proxy_url(proxy_prefix, absolute))
        elif stripped.startswith("#EXT-X-MEDIA") and 'URI="' in stripped:
            def repl(m: re.Match) -> str:
                absolute = urljoin(base_url, m.group(1))
                return f'URI="{proxy_url(proxy_prefix, absolute)}"'
            out.append(re.sub(r'URI="([^"]+)"', repl, stripped))
        else:
            out.append(line)
    return "\n".join(out) + "\n"
