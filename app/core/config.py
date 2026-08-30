from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    host: str = "0.0.0.0"
    port: int = 8080
    # Twitch resmi API (opsiyonel - durum/metadata icin)
    twitch_client_id: str = ""
    twitch_client_secret: str = ""
    # YouTube Data API v3 (opsiyonel - metadata icin)
    youtube_api_key: str = ""
    # Kick resmi public API tokeni (opsiyonel)
    kick_access_token: str = ""
    # HTTP davranisi
    http_impersonate: str = "chrome124"
    http_timeout: float = 15.0
    http_retries: int = 3
    cache_ttl_status: int = 30       # canli durum cache (sn)
    cache_ttl_manifest: int = 4      # master manifest cache (sn)
    ad_filter_enabled: bool = True
    # Bos birakilirsa guvenli yerlesik Twitch/Kick/YouTube CDN listesi kullanilir.
    hls_allowed_hosts: str = ""
    cors_origins: str = (
        "http://localhost:8080,http://127.0.0.1:8080,"
        "https://twitch.tv,https://www.twitch.tv,"
        "https://kick.com,https://www.kick.com,"
        "https://youtube.com,https://www.youtube.com"
    )

    # ---------- v2: bypass modulu ----------
    # direct | cf_server
    bypass_backend: str = "direct"
    cf_bypass_url: str = "http://localhost:8000"
    cf_bypass_mode: str = "mirror"          # mirror | cookies
    cf_cookie_ttl: int = 1800
    cf_protected_hosts: str = "kick.com"

    # ---------- v2: twitch client-integrity ----------
    # off | auto | force   (auto = sadece GQL CI istediginde cozer)
    twitch_integrity_mode: str = "auto"
    chromium_path: str = ""                  # bos = sistem PATH'ten bul
    integrity_ttl: int = 3600 * 12           # CI token cache suresi

    # ---------- v2: twitch yayin kaynagi ----------
    # direct | ttv_lol   (ttv_lol = upstream proxy, reklamsiz playlist)
    twitch_stream_source: str = "direct"
    ttv_lol_proxy: str = "https://api.ttv.lol"

    # ---------- v2: reklam filtre stratejisi ----------
    # scte35 | aggressive | none
    ad_filter_strategy: str = "scte35"

settings = Settings()
