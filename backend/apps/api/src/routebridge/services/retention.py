"""Scheduled data minimisation: purge expired idempotency keys, tracking links and stale sync/webhook payloads."""
from datetime import timedelta

from sqlalchemy import delete
from sqlmodel import Session

from routebridge.models.core import utc_now
from routebridge.models.plans import TrackingToken
from routebridge.models.reliability import IdempotencyRecord, MobileSyncEvent
from routebridge.models.webhooks import WebhookReceipt


def purge_expired(session: Session, sync_log_days: int = 90, webhook_days: int = 30) -> dict[str, int]:
    """Delete rows past their retention window. The audit trail itself is never purged here (it is append-only)."""
    now = utc_now()
    counts = {
        "idempotency_records": session.exec(delete(IdempotencyRecord).where(IdempotencyRecord.expires_at < now)).rowcount,
        "tracking_tokens": session.exec(delete(TrackingToken).where(TrackingToken.expires_at < now - timedelta(days=7))).rowcount,
        "mobile_sync_events": session.exec(delete(MobileSyncEvent).where(MobileSyncEvent.received_at < now - timedelta(days=sync_log_days))).rowcount,
        "webhook_receipts": session.exec(delete(WebhookReceipt).where(WebhookReceipt.received_at < now - timedelta(days=webhook_days))).rowcount,
    }
    session.commit()
    return counts
