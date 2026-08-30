from abc import ABC, abstractmethod
from app.core.models import ChannelStatus, StreamInfo


class BaseProvider(ABC):
    name: str

    @abstractmethod
    async def get_status(self, channel: str) -> ChannelStatus: ...

    @abstractmethod
    async def get_stream(self, channel: str) -> StreamInfo: ...