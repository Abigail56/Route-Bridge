import hashlib
import hmac
import json

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from routebridge.db.session import engine
from routebridge.config.settings import get_settings
from routebridge.integrations.svix import verify_svix
from routebridge.models.webhooks import WebhookAccepted, WebhookReceipt
from routebridge.services.clerk_sync import deactivate_clerk_user, sync_clerk_user

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _store_and_process(provider: str, payload: dict, event_id: str, payload_hash: str) -> WebhookAccepted:
    with Session(engine) as session:
        existing = session.exec(select(WebhookReceipt).where(WebhookReceipt.provider == provider, WebhookReceipt.event_id == event_id)).first()
        if existing:
            if existing.payload_hash != payload_hash:
                raise HTTPException(status_code=409, detail="Webhook event ID was reused with a different payload")
            return WebhookAccepted(status="duplicate", provider=provider, event_id=event_id, duplicate=True)
        session.add(WebhookReceipt(provider=provider, event_id=event_id, payload_hash=payload_hash, payload=payload))
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        if provider == "clerk":
            if payload.get("type") in {"user.created", "user.updated"}:
                sync_clerk_user(session, data)
            elif payload.get("type") == "user.deleted":
                deactivate_clerk_user(session, str(data.get("id") or data.get("user_id") or ""))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return WebhookAccepted(status="duplicate", provider=provider, event_id=event_id, duplicate=True)
    return WebhookAccepted(status="accepted", provider=provider, event_id=event_id, duplicate=False)


@router.post("/{provider}", response_model=WebhookAccepted)
async def receive_webhook(
    provider: str,
    request: Request,
    x_webhook_event_id: str | None = Header(default=None),
    svix_id: str | None = Header(default=None),
    svix_timestamp: str | None = Header(default=None),
    svix_signature: str | None = Header(default=None),
) -> WebhookAccepted:
    raw = await request.body()
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Body must be a JSON object") from exc

    settings = get_settings()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload_hash = hashlib.sha256(canonical).hexdigest()
    dev = settings.environment in {"development", "test"}

    if provider == "clerk" and settings.clerk_webhook_secret:
        # Clerk signs with Svix (svix-id / svix-timestamp / svix-signature); svix-id is the unique event id.
        verify_svix(settings.clerk_webhook_secret, svix_id, svix_timestamp, svix_signature, raw)
        event_id = svix_id or ""
    else:
        event_id = str(x_webhook_event_id or payload.get("id") or payload.get("event_id") or "")
        if not event_id:
            raise HTTPException(status_code=400, detail="X-Webhook-Event-ID or payload id is required")
        if not dev and (not settings.verify_webhook_signatures or not settings.webhook_signing_secret):
            raise HTTPException(status_code=503, detail="Webhook signature verification is required in this environment")
        if settings.verify_webhook_signatures:
            expected = hmac.HMAC(settings.webhook_signing_secret.encode(), canonical, hashlib.sha256).hexdigest()
            signature = request.headers.get("X-Webhook-Signature", "")
            if not settings.webhook_signing_secret or not hmac.compare_digest(signature, expected):
                raise HTTPException(status_code=401, detail="Invalid webhook signature")
    return await run_in_threadpool(_store_and_process, provider, payload, event_id, payload_hash)
