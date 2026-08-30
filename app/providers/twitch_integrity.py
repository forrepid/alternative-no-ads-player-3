import asyncio
import json
import logging
import shutil
import time

from app.core.config import settings

log = logging.getLogger("twitch.integrity")

# GQL'e gonderilecek persisted query ile ayni body uzerinden uretilir
_GQL_OPERATION = "PlaybackAccessToken"


class IntegrityTokenSolver:
    """Twitch client-integrity token cozucu.

    Twitch'in CI token'i web player JS'i ile hesaplanir ve tersine
    muhendisligi pratik degildir; bu yuzden streamlink.webbrowser
    yaklasiminin aynisi uygulanir: headless Chromium'da gercek
    twitch.tv sayfasi acilir, GQL istegi CDP ile yakalanir ve
    Client-Integrity header'i cikarilip cache'lenir.

    Bagimlilik (opsiyonel): playwright  ->  pip install playwright
                                            playwright install chromium
    Modul yoksa solver sessizce devre disi kalir (direct akis korunur).
    """

    def __init__(self) -> None:
        self._cache: tuple[str, float] | None = None  # (token, expire_ts)
        self._lock = asyncio.Lock()
        self._available: bool | None = None

    # ---------- kullanilabilirlik ----------
    def available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import playwright  # noqa: F401
            chromium = settings.chromium_path or shutil.which("chromium") \
                or shutil.which("chromium-browser") or shutil.which("google-chrome")
            self._available = True
            if chromium:
                log.info("integrity solver hazir (chromium: %s)", chromium)
        except ImportError:
            log.info("playwright yok - integrity solver devre disi")
            self._available = False
        return self._available

    # ---------- public API ----------
    async def get_token(self, force_refresh: bool = False) -> str | None:
        """Gecerli bir Client-Integrity tokeni dondurur; alinamazsa None."""
        if settings.twitch_integrity_mode == "off" or not self.available():
            return None
        if not force_refresh and self._cache and self._cache[1] > time.time():
            return self._cache[0]
        async with self._lock:
            # baska bir task az once yenilemis olabilir
            if not force_refresh and self._cache and self._cache[1] > time.time():
                return self._cache[0]
            token = await self._solve_in_browser()
            if token:
                self._cache = (token, time.time() + settings.integrity_ttl)
                log.info("client-integrity token yenilendi (ttl=%ds)",
                         settings.integrity_ttl)
            return token

    # ---------- tarayici cozumu ----------
    async def _solve_in_browser(self) -> str | None:
        """Headless Chromium'da twitch.tv acip GQL istegindeki
        Client-Integrity header'ini yakalar (CDP network interception)."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return None

        captured: dict[str, str] = {}

        async def on_request(request) -> None:
            if "gql.twitch.tv" in request.url and request.method == "POST":
                ci = request.headers.get("client-integrity")
                if ci:
                    captured["token"] = ci

        try:
            async with async_playwright() as pw:
                launch_kwargs: dict = {"headless": True}
                if settings.chromium_path:
                    launch_kwargs["executable_path"] = settings.chromium_path
                browser = await pw.chromium.launch(**launch_kwargs)
                page = await browser.new_page()
                page.on("request", on_request)
                # herhangi bir buyuk kanal GQL trafigi uretmek icin yeterli
                await page.goto("https://www.twitch.tv/directory",
                                wait_until="domcontentloaded", timeout=45000)
                # CI token ilk PlaybackAccessToken cagrisinda uretilir;
                # uretilmesi icin sayfanin JS'inin calismasini bekle
                for _ in range(30):
                    if "token" in captured:
                        break
                    await asyncio.sleep(1)
                await browser.close()
        except Exception as exc:  # noqa: BLE001
            log.warning("integrity solve hatasi: %s", exc)
            return None

        return captured.get("token")


solver = IntegrityTokenSolver()