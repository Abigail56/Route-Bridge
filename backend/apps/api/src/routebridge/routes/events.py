import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlmodel import Session, select

from routebridge.config.settings import get_settings
from routebridge.db.session import engine
from routebridge.models.events import OutboxEvent
from routebridge.services.events import stream_key
from routebridge.auth.authorization import tenant_member

router = APIRouter(prefix="/tenants/{tenant_id}/events", tags=["live-events"], dependencies=[Depends(tenant_member)])


def _sse(event_id: str, event_type: str, data: dict) -> str:
    return f"id: {event_id}\nevent: {event_type}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def _poll_outbox(tenant_id: UUID, cursor: datetime) -> list[OutboxEvent]:
    with Session(engine) as session:
        return list(session.exec(select(OutboxEvent).where(OutboxEvent.tenant_id == tenant_id, OutboxEvent.created_at > cursor).order_by(OutboxEvent.created_at).limit(100)).all())


async def _stream(tenant_id: UUID, request: Request, last_event_id: str | None):
    """Server-sent events for one tenant.

    Everything here must be non-blocking: this runs on the API's event loop, so a synchronous Redis `XREAD BLOCK` or
    database call would stall every other request for as long as it waits.
    """
    settings = get_settings()
    if settings.redis_url:
        client = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            key = stream_key(tenant_id)
            cursor = last_event_id
            if cursor is None:
                # A fresh connection should see new events only, not replay the tenant's whole history.
                newest = await client.xrevrange(key, count=1)
                cursor = newest[0][0] if newest else "0-0"
            while not await request.is_disconnected():
                records = await client.xread({key: cursor}, block=15000, count=50)
                if not records:
                    yield ": heartbeat\n\n"
                    continue
                for _, entries in records:
                    for event_id, fields in entries:
                        cursor = event_id
                        yield _sse(event_id, fields["event_type"], {"aggregate_type": fields["aggregate_type"], "aggregate_id": fields["aggregate_id"], "payload": json.loads(fields["payload"]), "occurred_at": fields["occurred_at"]})
        finally:
            await client.aclose()
        return

    # Local/test fallback: poll the durable outbox so the endpoint remains useful without Redis.
    cursor = datetime.now(timezone.utc)
    while not await request.is_disconnected():
        events = await asyncio.to_thread(_poll_outbox, tenant_id, cursor)
        for event in events:
            cursor = event.created_at
            yield _sse(str(event.id), event.event_type, {"aggregate_type": event.aggregate_type, "aggregate_id": str(event.aggregate_id), "payload": event.payload, "occurred_at": event.created_at.isoformat()})
        yield ": heartbeat\n\n"
        await asyncio.sleep(2)


@router.get("")
async def tenant_event_stream(tenant_id: UUID, request: Request, last_event_id: str | None = Header(default=None)) -> StreamingResponse:
    return StreamingResponse(_stream(tenant_id, request, last_event_id), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
