from sqlmodel import Session

from routebridge.models.orders import Order


def get_order_for_tenant(session: Session, tenant_id, order_id) -> Order | None:
    """Keep tenant-aware order lookup out of route handlers as the domain grows."""
    return session.get(Order, order_id)
