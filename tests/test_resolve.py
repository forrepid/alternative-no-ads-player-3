import unittest

from app.core.resolve import resolve_link
from app.providers.kick import _parse_variants


class ResolveTests(unittest.TestCase):
    def test_supported_links(self):
        cases = {
            "https://twitch.tv/Shroud": ("twitch", "shroud", None),
            "https://kick.com/test-user": ("kick", "test-user", None),
            "https://youtu.be/dQw4w9WgXcQ": ("youtube", None, "dQw4w9WgXcQ"),
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                result = resolve_link(value)
                self.assertIsNotNone(result)
                self.assertEqual((result.platform, result.channel, result.video_id), expected)

    def test_reserved_and_invalid_links_are_rejected(self):
        self.assertIsNone(resolve_link("https://twitch.tv/directory"))
        self.assertIsNone(resolve_link("https://example.com/channel"))

    def test_kick_variant_fixture(self):
        manifest = ("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=3000000,"
                    "RESOLUTION=1280x720,NAME=720p\nvideo.m3u8\n")
        variants = _parse_variants(manifest, "https://cdn.example/live/master.m3u8")
        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0].quality, "720p")
        self.assertEqual(variants[0].url, "https://cdn.example/live/video.m3u8")


if __name__ == "__main__":
    unittest.main()
