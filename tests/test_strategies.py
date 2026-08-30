"""Reklam filtre stratejileri ve bypass secimi icin testler.
Calistirma:  python -m pytest tests/ -v   (veya dogrudan: python tests/test_strategies.py)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.hls.strategies import apply_strategy  # noqa: E402
from app.hls.filter import rewrite_master_playlist  # noqa: E402

TWITCH_MEDIA_WITH_AD = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:2
#EXT-X-MEDIA-SEQUENCE:100
#EXTINF:2.000,
https://d1.example.com/seg100.ts
#EXTINF:2.000,
https://d1.example.com/seg101.ts
#EXT-X-DATERANGE:ID="stitched-ad-1234",CLASS="twitch-stitched-ad",START-DATE="2026-08-07T10:00:00Z",DURATION=30.0,X-TV-TWITCH-AD-URL="https://ads.example.com"
#EXT-X-DISCONTINUITY
#EXTINF:2.000,
https://d1.example.com/ad1.ts
#EXT-X-DATERANGE:ID="source-5678",CLASS="twitch-stream-content",START-DATE="2026-08-07T10:00:30Z"
#EXT-X-DISCONTINUITY
#EXTINF:2.000,
https://d1.example.com/seg102.ts
#EXT-X-CUE-OUT:30.0
#EXTINF:2.000,
https://d1.example.com/ad2.ts
#EXTINF:2.000,
https://d1.example.com/ad3.ts
#EXT-X-CUE-IN
#EXTINF:2.000,
seg103.ts
"""

MASTER_SAMPLE = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=8000000,RESOLUTION=1920x1080,NAME="1080p60"
https://d1.example.com/1080p/playlist.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=3000000,RESOLUTION=1280x720,NAME="720p60"
720p/playlist.m3u8
"""


def test_scte35_removes_stitched_ad():
    out, removed = apply_strategy("scte35", TWITCH_MEDIA_WITH_AD,
                                  "https://d1.example.com/")
    assert "ad1.ts" not in out, "stitched-ad segmenti kaldirilmaliydi"
    assert "seg100.ts" in out and "seg102.ts" in out
    assert removed >= 1


def test_scte35_removes_cue_out_block():
    out, removed = apply_strategy("scte35", TWITCH_MEDIA_WITH_AD,
                                  "https://d1.example.com/")
    assert "ad2.ts" not in out and "ad3.ts" not in out
    assert "CUE-OUT" not in out


def test_relative_uri_becomes_absolute():
    out, _ = apply_strategy("scte35", TWITCH_MEDIA_WITH_AD,
                            "https://d1.example.com/live/")
    assert "/api/hls/segment?url=https%3A%2F%2Fd1.example.com%2Flive%2Fseg103.ts" in out


def test_none_strategy_keeps_everything():
    out, removed = apply_strategy("none", TWITCH_MEDIA_WITH_AD,
                                  "https://d1.example.com/")
    assert removed == 0
    assert "ad1.ts" in out and "CUE-OUT" in out
    # goreli URI yine de mutlak olmali (player icin)
    assert "/api/hls/segment?url=https%3A%2F%2Fd1.example.com%2Fseg103.ts" in out


def test_unknown_strategy_falls_back_to_scte35():
    out, _ = apply_strategy("boyle-bir-sey-yok", TWITCH_MEDIA_WITH_AD,
                            "https://d1.example.com/")
    assert "ad1.ts" not in out


def test_aggressive_not_less_than_scte35():
    _, r1 = apply_strategy("scte35", TWITCH_MEDIA_WITH_AD,
                           "https://d1.example.com/")
    _, r2 = apply_strategy("aggressive", TWITCH_MEDIA_WITH_AD,
                           "https://d1.example.com/")
    assert r2 >= r1


def test_master_rewrite():
    out = rewrite_master_playlist(MASTER_SAMPLE, "https://d1.example.com/",
                                  "/api/hls/media")
    assert "/api/hls/media?url=https%3A%2F%2Fd1.example.com%2F1080p%2Fplaylist.m3u8" in out
    assert "/api/hls/media?url=https%3A%2F%2Fd1.example.com%2F720p%2Fplaylist.m3u8" in out


def test_master_rewrite_encodes_signed_query():
    body = "#EXTM3U\nvideo.m3u8?token=a%2Bb&expires=123\n"
    out = rewrite_master_playlist(body, "https://d1.example.com/live/",
                                  "/api/hls/media")
    assert "&expires=" not in out
    assert "%26expires%3D123" in out


def test_media_rewrites_key_and_map_uris():
    body = ('#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key.bin"\n'
            '#EXT-X-MAP:URI="init.mp4"\n#EXTINF:2,\nseg.ts\n')
    out, _ = apply_strategy("none", body, "https://d1.example.com/live/")
    assert "key.bin" in out and "/api/hls/segment?url=" in out
    assert "init.mp4" in out and "seg.ts" in out


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL  {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} test gecti")
    sys.exit(1 if failed else 0)
