import asyncio
import socket
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.core.proxy import proxy_url, validate_proxy_url


class ProxySecurityTests(unittest.TestCase):
    def test_proxy_url_encodes_nested_query(self):
        result = proxy_url("/api/hls/media", "https://video.googlevideo.com/a?x=1&y=2")
        self.assertEqual(result, (
            "/api/hls/media?url=https%3A%2F%2Fvideo.googlevideo.com%2Fa%3Fx%3D1%26y%3D2"))

    def test_proxy_rejects_unsafe_destinations(self):
        unsafe = (
            "http://usher.ttvnw.net/live.m3u8",
            "https://127.0.0.1/live.m3u8",
            "https://example.com/live.m3u8",
            "https://user:pass@usher.ttvnw.net/live.m3u8",
        )
        for url in unsafe:
            with self.subTest(url=url), self.assertRaises(HTTPException):
                asyncio.run(validate_proxy_url(url))

    def test_proxy_accepts_public_allowlisted_destination(self):
        result = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
        with patch.object(asyncio.BaseEventLoop, "getaddrinfo", return_value=result):
            url = "https://usher.ttvnw.net/live.m3u8"
            self.assertEqual(asyncio.run(validate_proxy_url(url)), url)

    def test_proxy_rejects_private_dns_result(self):
        result = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
        with patch.object(asyncio.BaseEventLoop, "getaddrinfo", return_value=result):
            with self.assertRaises(HTTPException):
                asyncio.run(validate_proxy_url("https://usher.ttvnw.net/live.m3u8"))


if __name__ == "__main__":
    unittest.main()
