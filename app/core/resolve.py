"""Tek bir linkten/kanal adindan platform + kanal/video tespiti."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass
class ResolvedLink:
    platform: str            # "twitch" | "kick" | "youtube" | "auto"
    kind: str                # "live" | "video"
    channel: str | None
    video_id: str | None
    original: str

    def to_dict(self) -> dict:
        return asdict(self)


_TWITCH_LIVE = re.compile(
    r"^(?:https?://)?(?:www\.|m\.)?twitch\.tv/(?P<channel>[A-Za-z0-9_]{3,25})/?(?:[?#].*)?$"
)
_TWITCH_VOD = re.compile(
    r"^(?:https?://)?(?:www\.|m\.)?twitch\.tv/videos/(?P<vid>\d+)(?:[?#].*)?$"
)
_KICK_LIVE = re.compile(
    r"^(?:https?://)?(?:www\.)?kick\.com/(?P<channel>[A-Za-z0-9_-]{2,25})/?(?:[?#].*)?$"
)
_KICK_VOD = re.compile(
    r"^(?:https?://)?(?:www\.)?kick\.com/(?P<channel>[A-Za-z0-9_-]+)/videos/(?P<vid>[\w-]+)(?:[?#].*)?$"
)
_YT_WATCH = re.compile(
    r"^(?:https?://)?(?:www\.|m\.)?youtube\.com/watch\?(?:.*&)?v=(?P<vid>[\w-]{11})"
)
_YT_SHORT = re.compile(r"^(?:https?://)?youtu\.be/(?P<vid>[\w-]{11})")
_YT_LIVE = re.compile(
    r"^(?:https?://)?(?:www\.)?youtube\.com/live/(?P<vid>[\w-]{11})"
)
_YT_SHORTS = re.compile(
    r"^(?:https?://)?(?:www\.)?youtube\.com/shorts/(?P<vid>[\w-]{11})"
)
_YT_HANDLE = re.compile(
    r"^(?:https?://)?(?:www\.)?youtube\.com/@(?P<channel>[\w.-]+)(?:/live)?/?(?:[?#].*)?$"
)
_YT_CHANNEL = re.compile(
    r"^(?:https?://)?(?:www\.)?youtube\.com/channel/(?P<channel>UC[\w-]{22})(?:/live)?/?(?:[?#].*)?$"
)

_TWITCH_RESERVED = {"directory", "p", "downloads", "turbo", "settings", "videos",
                    "moderator", "dashboard", "drops", "inventory", "subscriptions"}
_KICK_RESERVED = {"categories", "videos", "about", "terms", "privacy"}


def resolve_link(text: str) -> ResolvedLink | None:
    """Metni cozumler. Taninamazsa None. Duz kanal adi -> platform='auto'."""
    text = text.strip()
    if not text:
        return None

    m = _TWITCH_VOD.match(text)
    if m:
        return ResolvedLink("twitch", "video", None, m["vid"], text)
    m = _TWITCH_LIVE.match(text)
    if m and m["channel"].lower() not in _TWITCH_RESERVED:
        return ResolvedLink("twitch", "live", m["channel"].lower(), None, text)

    m = _KICK_VOD.match(text)
    if m:
        return ResolvedLink("kick", "video", m["channel"].lower(), m["vid"], text)
    m = _KICK_LIVE.match(text)
    if m and m["channel"].lower() not in _KICK_RESERVED:
        return ResolvedLink("kick", "live", m["channel"].lower(), None, text)

    m = _YT_WATCH.match(text) or _YT_SHORT.match(text) or _YT_LIVE.match(text) or _YT_SHORTS.match(text)
    if m:
        return ResolvedLink("youtube", "video", None, m["vid"], text)
    m = _YT_HANDLE.match(text) or _YT_CHANNEL.match(text)
    if m:
        return ResolvedLink("youtube", "live", m["channel"], None, text)

    # URL degilse: duz kanal adi -> platform otomatik tespit edilecek
    if re.fullmatch(r"[A-Za-z0-9_]{2,25}", text):
        return ResolvedLink("auto", "live", text.lower(), None, text)

    return None


if __name__ == "__main__":
    # Testler: python app/core/resolve.py
    cases = [
        ("https://www.twitch.tv/Shroud", ("twitch", "live", "shroud", None)),
        ("twitch.tv/videos/123456789", ("twitch", "video", None, "123456789")),
        ("https://kick.com/gokhanoner", ("kick", "live", "gokhanoner", None)),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", ("youtube", "video", None, "dQw4w9WgXcQ")),
        ("https://youtu.be/dQw4w9WgXcQ", ("youtube", "video", None, "dQw4w9WgXcQ")),
        ("https://www.youtube.com/@LinusTechTips/live", ("youtube", "live", "LinusTechTips", None)),
        ("gokhanoner", ("auto", "live", "gokhanoner", None)),
        ("https://twitch.tv/directory", None),
        ("???", None),
    ]
    for url, expected in cases:
        r = resolve_link(url)
        got = None if r is None else (r.platform, r.kind, r.channel, r.video_id)
        assert got == expected, f"FAIL {url}: {got} != {expected}"
        print(f"OK  {url} -> {got}")
    print("Tum testler gecti.")