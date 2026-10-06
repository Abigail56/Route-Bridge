from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from routebridge.db.session import get_session
from routebridge.models.core import Tenant
from routebridge.models.operations import PaymentRecord, ReconciliationItem
from routebridge.models.orders import Order
from routebridge.models.workflows import Notification, ReconciliationRead, ReconciliationResolve
from routebridge.services.notifications import TEMPLATES, queue_notification as enqueue_notification
from routebridge.auth.authorization import tenant_member, tenant_roles
from routebridge.services.events import record_event

FINANCE_ROLES = ("tenant_owner", "tenant_admin", "operations_manager", "finance")
NOTIFY_ROLES = ("tenant_owner", "tenant_admin", "dispatcher", "operations_manager")

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["settlements"], dependencies=[Depends(tenant_member)])


def require_tenant(session: Session, tenant_id: UUID) -> None:
    if session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found")


@router.get("/reconciliation", response_model=list[ReconciliationRead])
def list_reconciliation(tenant_id: UUID, session: Session = Depends(get_session)) -> list[ReconciliationItem]:
    require_tenant(session, tenant_id)
    return list(session.exec(select(ReconciliationItem).where(ReconciliationItem.tenant_id == tenant_id)).all())


@router.post("/reconciliation/{item_id}/resolve", response_model=ReconciliationRead, dependencies=[Depends(tenant_roles(*FINANCE_ROLES))])
def resolve_reconciliation(
    tenant_id: UUID,
    item_id: UUID,
    payload: ReconciliationResolve,
    session: Session = Depends(get_session),
) -> ReconciliationItem:
    require_tenant(session, tenant_id)
    item = session.get(ReconciliationItem, item_id)
    if item is None or item.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Reconciliation item not found")
    item.status = "resolved"
    item.resolution_note = payload.resolution_note
    payment = session.get(PaymentRecord, item.payment_id)
    if payment:
        payment.reconciliation_status = "resolved"
    record_event(session, tenant_id, "reconciliation.resolved", "reconciliation_item", item.id, {"payment_id": str(item.payment_id), "resolution_note": payload.resolution_note})
    session.commit()
    session.refresh(item)
    return item


@router.post("/orders/{order_id}/notifications", response_model=Notification, status_code=201, dependencies=[Depends(tenant_roles(*NOTIFY_ROLES))])
def queue_notification(
    tenant_id: UUID,
    order_id: UUID,
    channel: str,
    template: str,
    session: Session = Depends(get_session),
) -> Notification:
    require_tenant(session, tenant_id)
    if template not in TEMPLATES:
        raise HTTPException(status_code=422, detail=f"Unknown template; choose one of: {', '.join(sorted(TEMPLATES))}")
    if channel not in {"sms", "whatsapp"}:
        raise HTTPException(status_code=422, detail="channel must be sms or whatsapp")
    order = session.get(Order, order_id)
    if order is None or order.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Order not found")
    notification = enqueue_notification(session, order, template, channel=channel)
    if notification is None:
        raise HTTPException(status_code=409, detail="Customer has opted out of this channel or has no contact")
    session.commit()
    session.refresh(notification)
    return notification
