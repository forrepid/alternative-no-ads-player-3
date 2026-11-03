import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.providers.twitch import TwitchProvider
from app.providers.youtube import YouTubeProvider


class ProviderStreamTests(unittest.TestCase):
    def test_twitch_uses_gql_token_value_without_double_json_encoding(self):
        provider = TwitchProvider()
        token = {
            "signature": "signature",
            "value": '{"channel":"demo"}',
        }
        manifest = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000\nvariant.m3u8\n"

        async def run():
            with patch.object(provider, "_playback_access_token", AsyncMock(return_value=token)), \
                 patch("app.providers.twitch.http.get_text", AsyncMock(return_value=manifest)) as get_text:
                info = await provider._stream_direct("demo")
                return info, get_text.await_args.args[0]

        info, upstream_url = asyncio.run(run())
        self.assertTrue(info.is_live)
        self.assertIn("token=%7B%22channel%22%3A%22demo%22%7D", upstream_url)
        self.assertNotIn("token=%22%7B", upstream_url)

    def test_youtube_channel_id_uses_channel_live_url_and_decodes_hls(self):
        provider = YouTubeProvider()
        channel = "UC4R8DWoMoI7CAwX8_LjQHig"
        hls = "https://manifest.googlevideo.com/api/manifest/hls?x=1&y=2"
        page = ('{"isLiveContent":true,"hlsManifestUrl":"https:\\/\\/'
                'manifest.googlevideo.com\\/api\\/manifest\\/hls?x=1\\u0026y=2"}')
        manifest = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000\nvariant.m3u8\n"

        async def get_text(url):
            return page if "/channel/" in url else manifest

        async def run():
            with patch("app.providers.youtube.http.get_text", side_effect=get_text) as mocked:
                info = await provider.get_stream(channel)
                return info, mocked.await_args_list

        info, calls = asyncio.run(run())
        self.assertTrue(info.is_live)
        self.assertEqual(calls[0].args[0], f"https://www.youtube.com/channel/{channel}/live")
        self.assertEqual(calls[1].args[0], hls)


if __name__ == "__main__":
    unittest.main()
