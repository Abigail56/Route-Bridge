from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from routebridge.db.session import get_session
from routebridge.models.access import TenantMembership, User
from routebridge.models.catalog import (
    MerchantCreate,
    ServiceZone,
    ServiceZoneCreate,
    TenantCreate,
    TenantRead,
)
from routebridge.models.core import Country, OperatingArea, Tenant, TenantArea
from routebridge.models.orders import Merchant
from routebridge.services.events import record_event
from routebridge.auth.authorization import tenant_roles, TenantPrincipal
from routebridge.auth.dependencies import get_optional_user
from routebridge.config.settings import get_settings
from routebridge.integrations.clerk import ClerkUser
from routebridge.services.platform import is_platform_admin


def require_authenticated(clerk_user: ClerkUser | None = Depends(get_optional_user)) -> ClerkUser | None:
    """Tenant-less admin routes: require a verified Clerk user (dev/test without Clerk auth is exempt)."""
    settings = get_settings()
    if clerk_user is None and not (settings.environment in {"development", "test"} and not settings.require_clerk_auth):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clerk authentication required")
    return clerk_user

def require_platform_admin(clerk_user: ClerkUser | None = Depends(get_optional_user), session: Session = Depends(get_session)) -> ClerkUser | None:
    """Platform-operator actions: the caller must be a platform administrator (database list or the bootstrap settings list)."""
    settings = get_settings()
    if clerk_user is None:
        if settings.environment in {"development", "test"} and not settings.require_clerk_auth:
            return None
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clerk authentication required")
    if not is_platform_admin(session, clerk_user.subject):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform administrator access required")
    return clerk_user


router = APIRouter(prefix="/admin", tags=["administration"], dependencies=[Depends(require_authenticated)])


@router.get("/operating-areas", response_model=list[OperatingArea])
def list_operating_areas(session: Session = Depends(get_session)) -> list[OperatingArea]:
    return list(session.exec(select(OperatingArea).where(OperatingArea.status == "active")).all())


@router.post("/tenants", response_model=TenantRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_platform_admin)])
def create_tenant(
    payload: TenantCreate,
    session: Session = Depends(get_session),
    clerk_user: ClerkUser | None = Depends(get_optional_user),
) -> Tenant:
    tenant = Tenant(name=payload.name)
    session.add(tenant)
    session.flush()
    if clerk_user is not None:
        # The creator becomes the first tenant owner so the new workspace is usable immediately.
        user = session.exec(select(User).where(User.clerk_user_id == clerk_user.subject)).first()
        if user is None:
            user = User(clerk_user_id=clerk_user.subject, email=clerk_user.claims.get("email"), full_name=clerk_user.claims.get("name"))
            session.add(user)
            session.flush()
        session.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role="tenant_owner"))
    record_event(session, tenant.id, "tenant.created", "tenant", tenant.id, {"name": tenant.name})
    session.commit()
    session.refresh(tenant)
    return tenant


@router.post("/tenants/{tenant_id}/areas/{operating_area_id}", response_model=TenantArea, status_code=201)
def attach_tenant_area(
    tenant_id: UUID,
    operating_area_id: UUID,
    _: TenantPrincipal = Depends(tenant_roles("tenant_owner", "tenant_admin")),
    session: Session = Depends(get_session),
) -> TenantArea:
    if session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if session.get(OperatingArea, operating_area_id) is None:
        raise HTTPException(status_code=404, detail="Operating area not found")
    existing = session.exec(
        select(TenantArea).where(
            TenantArea.tenant_id == tenant_id,
            TenantArea.operating_area_id == operating_area_id,
        )
    ).first()
    if existing:
        return existing
    area = session.get(OperatingArea, operating_area_id)
    assert area is not None
    country = session.get(Country, area.country_id)
    tenant_area = TenantArea(
        tenant_id=tenant_id,
        operating_area_id=operating_area_id,
        local_currency=country.default_currency if country else "NGN",
        timezone=area.timezone,
    )
    session.add(tenant_area)
    session.commit()
    session.refresh(tenant_area)
    return tenant_area


@router.post("/tenants/{tenant_id}/merchants", response_model=Merchant, status_code=201)
def create_merchant(
    tenant_id: UUID,
    payload: MerchantCreate,
    _: TenantPrincipal = Depends(tenant_roles("tenant_owner", "tenant_admin")),
    session: Session = Depends(get_session),
) -> Merchant:
    if session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    merchant = Merchant(tenant_id=tenant_id, **payload.model_dump())
    session.add(merchant)
    session.flush()
    record_event(session, tenant_id, "merchant.created", "merchant", merchant.id, {"name": merchant.name})
    session.commit()
    session.refresh(merchant)
    return merchant


@router.get("/tenants/{tenant_id}/merchants", response_model=list[Merchant])
def list_merchants(tenant_id: UUID, _: TenantPrincipal = Depends(tenant_roles("tenant_owner", "tenant_admin")), session: Session = Depends(get_session)) -> list[Merchant]:
    if session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return list(session.exec(select(Merchant).where(Merchant.tenant_id == tenant_id)).all())


@router.post("/tenants/{tenant_id}/zones", response_model=ServiceZone, status_code=201)
def create_zone(
    tenant_id: UUID,
    payload: ServiceZoneCreate,
    _: TenantPrincipal = Depends(tenant_roles("tenant_owner", "tenant_admin")),
    session: Session = Depends(get_session),
) -> ServiceZone:
    if session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if session.get(OperatingArea, payload.operating_area_id) is None:
        raise HTTPException(status_code=404, detail="Operating area not found")
    zone = ServiceZone(tenant_id=tenant_id, **payload.model_dump())
    session.add(zone)
    session.flush()
    record_event(session, tenant_id, "service_zone.created", "service_zone", zone.id, {"name": zone.name})
    session.commit()
    session.refresh(zone)
    return zone
