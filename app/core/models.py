from enum import Enum

from pydantic import BaseModel, Field


class Platform(str, Enum):
    kick = "kick"
    twitch = "twitch"
    youtube = "youtube"


class StreamVariant(BaseModel):
    quality: str
    url: str
    resolution: str | None = None
    bandwidth: int | None = None
    kind: str = "video"                 # video | audio
    codecs: str | None = None
    frame_rate: float | None = None


class ChannelStatus(BaseModel):
    platform: Platform
    channel: str
    is_live: bool
    title: str | None = None
    category: str | None = None
    viewers: int | None = None
    thumbnail: str | None = None
    started_at: str | None = None
    error: str | None = None


class StreamInfo(BaseModel):
    platform: Platform
    channel: str
    is_live: bool
    title: str | None = None
    master_playlist: str | None = None        # proxied URL
    variants: list[StreamVariant] = Field(default_factory=list)
    ads_filtered: bool = False
    # v2: opsiyonel alanlar (mevcut istemcileri bozmaz)
    source: str | None = None      # direct | ttv_lol | official
    error: str | None = None
    viewers: int | None = None
    category: str | None = None
    started_at: str | None = None
