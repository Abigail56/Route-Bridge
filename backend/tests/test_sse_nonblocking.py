import asyncio
from uuid import uuid4

from routebridge.config.settings import get_settings
from routebridge.routes import events


class _FakeRequest:
    def __init__(self) -> None:
        self.disconnected = False

    async def is_disconnected(self) -> bool:
        return self.disconnected


class _FakeRedis:
    """Async Redis stand-in: an empty stream whose XREAD blocks (asynchronously) for 50 ms, then times out."""

    created: list["_FakeRedis"] = []

    def __init__(self) -> None:
        self.closed = False
        self.reads: list[dict] = []
        _FakeRedis.created.append(self)

    @classmethod
    def from_url(cls, *_args, **_kwargs) -> "_FakeRedis":
        return cls()

    async def xrevrange(self, *_args, **_kwargs):
        return [("1700000000000-3", {})]  # the newest existing event id

    async def xread(self, streams, block, count):
        self.reads.append(streams)
        await asyncio.sleep(0.05)
        return []

    async def aclose(self) -> None:
        self.closed = True


def test_redis_stream_does_not_block_the_event_loop_and_starts_from_now(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "redis_url", "redis://fake")
    monkeypatch.setattr(events, "Redis", _FakeRedis)
    _FakeRedis.created.clear()
    tenant_id = uuid4()

    async def scenario() -> tuple[int, list[str]]:
        request = _FakeRequest()
        ticks = 0
        stop = False

        async def ticker() -> None:  # a stand-in for "every other request the API has to serve"
            nonlocal ticks
            while not stop:
                await asyncio.sleep(0.005)
                ticks += 1

        task = asyncio.create_task(ticker())
        chunks: list[str] = []
        async for chunk in events._stream(tenant_id, request, None):
            chunks.append(chunk)
            if len(chunks) == 3:
                request.disconnected = True
        stop = True
        await task
        return ticks, chunks

    ticks, chunks = asyncio.run(scenario())
    assert chunks == [": heartbeat\n\n"] * 3
    assert ticks >= 5  # a blocking XREAD would starve the loop (0-1 ticks) during the 3 x 50 ms of reads; Windows timers tick every ~15 ms
    fake = _FakeRedis.created[0]
    assert fake.closed  # the connection is released when the client goes away
    assert list(fake.reads[0].values()) == ["1700000000000-3"]  # a fresh connection resumes from the newest event, not "0-0"


def test_reconnect_with_last_event_id_resumes_from_it(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "redis_url", "redis://fake")
    monkeypatch.setattr(events, "Redis", _FakeRedis)
    _FakeRedis.created.clear()

    async def scenario() -> None:
        request = _FakeRequest()
        async for _ in events._stream(uuid4(), request, "1699999999999-0"):
            request.disconnected = True

    asyncio.run(scenario())
    assert list(_FakeRedis.created[0].reads[0].values()) == ["1699999999999-0"]
