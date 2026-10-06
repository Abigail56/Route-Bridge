"""Signed order intake for storefronts (Shopify/WooCommerce-style) and other systems.

Each tenant has its own signing secret, derived from the platform secret so nothing extra is stored. The signature
covers `timestamp.body`, and requests older than 5 minutes are rejected (replay control).
"""
import hashlib
import hmac
import json
import time
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from routebridge.auth.authorization import tenant_roles
from routebridge.config.settings import get_settings
from routebridge.db.session import get_session
from routebridge.models.core import Tenant
from routebridge.models.webhooks import WebhookReceipt
from routebridge.routes.orders import create_order
from routebridge.services.connectors import CONNECTORS, ConnectorError

REPLAY_WINDOW_SECONDS = 300
router = APIRouter(tags=["order-intake"])


def tenant_signing_secret(tenant_id: UUID) -> str:
    settings = get_settings()
    if not settings.webhook_signing_secret:
        raise HTTPException(status_code=503, detail="Webhook signing is not configured")
    return hmac.new(settings.webhook_signing_secret.encode(), f"order-intake:{tenant_id}".encode(), hashlib.sha256).hexdigest()


def sign(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


@router.get("/tenants/{tenant_id}/integrations/order-webhook", dependencies=[Depends(tenant_roles("tenant_owner", "tenant_admin"))])
def order_webhook_details(tenant_id: UUID, session: Session = Depends(get_session)) -> dict:
    """What a merchant needs to configure their storefront: URL pattern and the tenant signing secret."""
    if session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {
        "url": f"{get_settings().api_v1_prefix}/webhooks/orders/{tenant_id}?source=shopify|woocommerce|generic&merchant_id=<merchant uuid>",
        "signing_secret": tenant_signing_secret(tenant_id),
        "headers": ["X-Webhook-Timestamp: <unix seconds>", "X-Webhook-Signature: hex(HMAC-SHA256(secret, timestamp + '.' + raw_body))", "X-Webhook-Event-ID: <unique id>"],
        "replay_window_seconds": REPLAY_WINDOW_SECONDS,
    }


@router.post("/webhooks/orders/{tenant_id}", status_code=202)
async def receive_order(
    tenant_id: UUID,
    request: Request,
    merchant_id: UUID = Query(),
    source: str = Query(default="generic"),
    x_webhook_timestamp: str | None = Header(default=None),
    x_webhook_signature: str | None = Header(default=None),
    x_webhook_event_id: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> dict:
    if source not in CONNECTORS:
        raise HTTPException(status_code=422, detail=f"Unknown source; choose one of: {', '.join(CONNECTORS)}")
    body = await request.body()
    if len(body) > 1_000_000:
        raise HTTPException(status_code=413, detail="Payload too large")
    secret = tenant_signing_secret(tenant_id)
    if not x_webhook_timestamp or not x_webhook_signature:
        raise HTTPException(status_code=401, detail="Missing signature headers")
    try:
        age = abs(time.time() - float(x_webhook_timestamp))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid timestamp") from exc
    if age > REPLAY_WINDOW_SECONDS:
        raise HTTPException(status_code=401, detail="Webhook timestamp outside the allowed window")
    if not hmac.compare_digest(x_webhook_signature, sign(secret, x_webhook_timestamp, body)):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    if session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Body must be a JSON object") from exc

    event_id = x_webhook_event_id or str(payload.get("id") or payload.get("number") or payload.get("external_ref") or "")
    if not event_id:
        raise HTTPException(status_code=400, detail="X-Webhook-Event-ID or an order id is required")
    provider = f"orders:{tenant_id}:{source}"
    payload_hash = hashlib.sha256(body).hexdigest()
    existing = session.exec(select(WebhookReceipt).where(WebhookReceipt.provider == provider, WebhookReceipt.event_id == event_id)).first()
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise HTTPException(status_code=409, detail="Event ID was reused with a different payload")
        return {"status": "duplicate", "event_id": event_id}

    try:
        order_input = CONNECTORS[source](payload, merchant_id)
    except (ConnectorError, ValidationError, TypeError, KeyError) as exc:
        session.add(WebhookReceipt(provider=provider, event_id=event_id, payload_hash=payload_hash, payload={"error": "unmappable"}, status="rejected"))
        session.commit()
        detail = exc.errors(include_input=False) if isinstance(exc, ValidationError) else str(exc)
        raise HTTPException(status_code=422, detail=detail) from exc
    try:
        order = create_order(tenant_id, order_input, f"webhook-{source}-{event_id}"[:200], session)
    except HTTPException as exc:
        if exc.status_code == 409:  # same storefront order delivered twice under a new event id
            return {"status": "duplicate", "event_id": event_id}
        raise
    session.add(WebhookReceipt(provider=provider, event_id=event_id, payload_hash=payload_hash, payload={"order_id": str(order.id)}, status="processed"))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
    return {"status": "accepted", "event_id": event_id, "order_id": order.id}
