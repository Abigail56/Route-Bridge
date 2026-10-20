"""Staff view of an order's tracking-link space and its evidence of delivery."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from routebridge.auth.authorization import tenant_member
from routebridge.db.session import get_session
from routebridge.models.orders import Order
from routebridge.services import order_extras

router = APIRouter(prefix="/tenants/{tenant_id}/orders", tags=["order-extras"], dependencies=[Depends(tenant_member)])


def _order(session: Session, tenant_id: UUID, order_id: UUID) -> Order:
    order = session.get(Order, order_id)
    if order is None or order.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("/{order_id}/tracking-share")
def get_tracking_share(tenant_id: UUID, order_id: UUID, session: Session = Depends(get_session)) -> dict:
    return order_extras.tracking_share(session, _order(session, tenant_id, order_id))


@router.post("/{order_id}/tracking-share/send", status_code=201)
def send_tracking_share(tenant_id: UUID, order_id: UUID, channel: str, session: Session = Depends(get_session)) -> dict:
    order = _order(session, tenant_id, order_id)
    order_extras.send_tracking_link(session, order, channel, by="staff")
    return order_extras.tracking_share(session, order)


@router.get("/{order_id}/evidence")
def get_evidence(tenant_id: UUID, order_id: UUID, session: Session = Depends(get_session)) -> dict:
    return order_extras.evidence(session, _order(session, tenant_id, order_id), staff=True)
