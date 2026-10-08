"""Driver-device API: short-lived token issue (staff) plus job pull and offline sync (driver token)."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ConfigDict
from sqlmodel import Field, Session, SQLModel, select

from routebridge.auth.authorization import tenant_roles
from routebridge.db.session import get_session
from routebridge.integrations.driver_tokens import driver_principal, issue_driver_token
from routebridge.integrations.rate_limit import limiter
from routebridge.models.operations import Driver, DriverAssignment
from routebridge.models.push import PushSubscription
from routebridge.models.orders import Customer, DeliveryJob, Order
from routebridge.models.reliability import MobileSyncRequest, MobileSyncResponse
from routebridge.routes.operations import issue_delivery_otp, require_tenant
from routebridge.routes.orders import to_order_reads
from routebridge.routes.reliability import _driver_has_job, process_events
from routebridge.config.settings import get_settings
from routebridge.providers import get_telephony_provider
from routebridge.services.events import record_event
from routebridge.services.flags import enabled
from routebridge.services import storage

OPS_ROLES = ("tenant_owner", "tenant_admin", "dispatcher", "operations_manager")
ACTIVE_STATUSES = {"assigned", "accepted", "en_route", "arrived", "rescheduled"}

staff_router = APIRouter(prefix="/tenants/{tenant_id}/drivers", tags=["driver-devices"], dependencies=[Depends(tenant_roles(*OPS_ROLES))])
router = APIRouter(prefix="/driver/tenants/{tenant_id}", tags=["driver-devices"])


@staff_router.post("/{driver_id}/token")
def issue_token(tenant_id: UUID, driver_id: UUID, session: Session = Depends(get_session)) -> dict:
    """Issue a short-lived device token (hand it over via QR/SMS). Rotating it simply issues another."""
    driver = session.get(Driver, driver_id)
    if driver is None or driver.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Driver not found for tenant")
    token, expires_in = issue_driver_token(driver)
    record_event(session, tenant_id, "driver.token_issued", "driver", driver.id, {"expires_in": expires_in})
    session.commit()
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in}


def _mask_phone(phone: str) -> str:
    return "*" * max(0, len(phone) - 4) + phone[-4:]


class DriverPhoto(SQLModel):
    model_config = ConfigDict(extra="forbid")

    data_url: str = Field(min_length=30, max_length=80000)


MAX_PHOTO_BYTES = 45_000
_PHOTO_MAGIC = {"jpeg": b"\xff\xd8\xff", "png": b"\x89PNG\r\n\x1a\n", "webp": b"RIFF"}


def check_photo(data_url: str) -> str:
    """Accept only a small JPEG/PNG/WebP given as a data URL whose bytes really are that image type."""
    import base64
    import binascii
    import re

    match = re.fullmatch(r"data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/]+={0,2})", data_url)
    if not match:
        raise HTTPException(status_code=422, detail="The picture must be a JPEG, PNG or WebP image.")
    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="The picture could not be read.") from exc
    if len(raw) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail=f"The picture is too big ({len(raw) // 1000} KB). It is shrunk automatically in the app; try a different photo.")
    if not raw.startswith(_PHOTO_MAGIC[match.group(1)]) or (match.group(1) == "webp" and raw[8:12] != b"WEBP"):
        raise HTTPException(status_code=422, detail="The file is not really that kind of image.")
    return data_url


@staff_router.put("/{driver_id}/photo")
def set_driver_photo(tenant_id: UUID, driver_id: UUID, payload: DriverPhoto, session: Session = Depends(get_session)) -> dict:
    driver = session.get(Driver, driver_id)
    if driver is None or driver.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Driver not found")
    driver.photo = check_photo(payload.data_url)
    session.add(driver)
    record_event(session, tenant_id, "driver.photo_changed", "driver", driver.id, {})
    session.commit()
    return {"photo": driver.photo}


@staff_router.delete("/{driver_id}/photo")
def remove_driver_photo(tenant_id: UUID, driver_id: UUID, session: Session = Depends(get_session)) -> dict:
    driver = session.get(Driver, driver_id)
    if driver is None or driver.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Driver not found")
    driver.photo = None
    session.add(driver)
    session.commit()
    return {"photo": None}


@router.get("/jobs")
def my_jobs(tenant_id: UUID, driver: Driver = Depends(driver_principal), session: Session = Depends(get_session)) -> list[dict]:
    """The driver's active work, in a compact shape for low-bandwidth caching on the device."""
    assignments = session.exec(select(DriverAssignment).where(DriverAssignment.driver_id == driver.id, DriverAssignment.status == "active")).all()
    jobs = [j for j in (session.get(DeliveryJob, a.delivery_job_id) for a in assignments) if j is not None and j.status in ACTIVE_STATUSES]
    orders = {o.id: o for o in session.exec(select(Order).where(Order.id.in_([j.order_id for j in jobs]))).all()} if jobs else {}
    reads = {r.delivery_job_id: r for r in to_order_reads(session, list(orders.values()))}
    result = []
    for job in jobs:
        read, order = reads.get(job.id), orders.get(job.order_id)
        customer = session.get(Customer, order.customer_id) if order else None
        result.append(
            {
                "job_id": job.id,
                "reference": read.external_ref if read else None,
                "status": job.status,
                "customer_name": read.customer_name if read else None,
                "customer_phone_masked": _mask_phone(customer.phone) if customer else None,  # real number stays server-side
                "address": read.address_text if read else None,
                "landmark": read.landmark if read else None,
                "plus_code": read.plus_code if read else None,
                "latitude": read.latitude if read else None,
                "longitude": read.longitude if read else None,
                "cod_amount": str(order.cod_amount) if order else None,
                "location_score": read.location_score if read else None,
                "recipient_available": read.recipient_available if read else None,
                "window_start": read.window_start if read else None,
                "window_end": read.window_end if read else None,
            }
        )
    return result


@router.post("/sync", response_model=MobileSyncResponse)
def driver_sync(tenant_id: UUID, request: MobileSyncRequest, driver: Driver = Depends(driver_principal), session: Session = Depends(get_session)) -> MobileSyncResponse:
    """Offline-queue flush: transitions, proof (with OTP code), COD payment, location corrections and GPS pings.
    Only jobs actively assigned to this driver are accepted."""
    retry_after = limiter.check(f"driver-sync:{driver.id}", limit=30, window_seconds=60)
    if retry_after:
        raise HTTPException(status_code=429, detail="Too many sync requests", headers={"Retry-After": str(retry_after)})
    return process_events(session, tenant_id, request.events, driver)


@router.post("/jobs/{job_id}/otp", status_code=201)
def request_otp(tenant_id: UUID, job_id: UUID, driver: Driver = Depends(driver_principal), session: Session = Depends(get_session)) -> dict:
    """Ask the server to text the customer a delivery code (needs connectivity; the code is verified server-side)."""
    require_tenant(session, tenant_id)
    job = session.get(DeliveryJob, job_id)
    if job is None or job.tenant_id != tenant_id or not _driver_has_job(session, driver, job):
        raise HTTPException(status_code=404, detail="Job not found")
    result = issue_delivery_otp(tenant_id, job_id, session)
    result.pop("debug_code", None)  # drivers must never see the code
    return result


def _own_job(session: Session, tenant_id: UUID, driver: Driver, job_id: UUID) -> DeliveryJob:
    job = session.get(DeliveryJob, job_id)
    if job is None or job.tenant_id != tenant_id or not _driver_has_job(session, driver, job):
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _require_flag(name: str) -> None:
    if not enabled(name):
        raise HTTPException(status_code=404, detail="Not available")  # indistinguishable from a missing route


@router.post("/jobs/{job_id}/call")
def call_customer(tenant_id: UUID, job_id: UUID, driver: Driver = Depends(driver_principal), session: Session = Depends(get_session)) -> dict:
    """The driver calls the customer once they have ARRIVED at the address (not before).

    direct: the customer's number is returned to this one assigned driver so the phone's own dialer can place the call. It works with no
            telephony account. Every request is recorded.
    masked: a call is bridged through the telephony gateway and no number is returned.
    """
    _require_flag("masked_calls")
    job = _own_job(session, tenant_id, driver, job_id)
    if job.status != "arrived":
        raise HTTPException(status_code=409, detail="You can call the customer once you have arrived at their address.")
    retry_after = limiter.check(f"driver-call:{driver.id}", limit=10, window_seconds=300)
    if retry_after:
        raise HTTPException(status_code=429, detail="Too many calls requested", headers={"Retry-After": str(retry_after)})
    order = session.get(Order, job.order_id)
    customer = session.get(Customer, order.customer_id) if order else None
    if customer is None or customer.status != "active":
        raise HTTPException(status_code=409, detail="No customer contact available")
    settings = get_settings()
    gateway = settings.telephony_provider == "http" and bool(settings.telephony_api_url)
    masked = settings.driver_call_mode == "masked" or (settings.driver_call_mode == "auto" and gateway)
    if not masked:
        record_event(session, tenant_id, "driver.call_requested", "delivery_job", job.id, {"driver_id": str(driver.id), "mode": "direct"}, actor_type="driver_device", actor_id=driver.id)
        session.commit()
        return {"status": "dial", "dial_number": customer.phone}
    try:
        call_id = get_telephony_provider().bridge_call(driver.phone, customer.phone, order.external_ref)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Calling is temporarily unavailable") from exc
    record_event(session, tenant_id, "driver.call_requested", "delivery_job", job.id, {"driver_id": str(driver.id), "call_id": call_id, "mode": "masked"}, actor_type="driver_device", actor_id=driver.id)
    session.commit()
    return {"status": "connecting", "call_id": call_id}


class UploadRequest(SQLModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["photo", "signature"] = "photo"
    content_type: str = "image/jpeg"


@router.post("/jobs/{job_id}/uploads")
def request_upload(tenant_id: UUID, job_id: UUID, payload: UploadRequest, request: Request, driver: Driver = Depends(driver_principal), session: Session = Depends(get_session)) -> dict:
    """Get a place to put a delivery photo/signature. With S3 configured this is a presigned PUT URL (the image goes
    straight to object storage); otherwise a PUT endpoint on this API. Put `object_url` in the proof payload."""
    _require_flag("driver_photo_uploads")
    job = _own_job(session, tenant_id, driver, job_id)
    try:
        key = storage.new_object_key(tenant_id, job.id, payload.kind, payload.content_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    settings = get_settings()
    if storage.s3_enabled(settings):
        upload_url = storage.presign_for(settings, "PUT", key)
    else:
        upload_url = f"{str(request.base_url).rstrip('/')}{settings.api_v1_prefix}/driver/tenants/{tenant_id}/media/{key}"
    return {"upload_url": upload_url, "method": "PUT", "headers": {"Content-Type": payload.content_type}, "object_url": f"media://{key}", "max_bytes": storage.MAX_UPLOAD_BYTES, "needs_auth": not storage.s3_enabled(settings)}


@router.put("/media/{key:path}", status_code=201)
async def put_media(tenant_id: UUID, key: str, request: Request, driver: Driver = Depends(driver_principal), session: Session = Depends(get_session)) -> dict:
    """Local-disk upload target (used when S3 is not configured). The key must belong to a job assigned to this driver."""
    _require_flag("driver_photo_uploads")
    parts = key.split("/")
    if len(parts) != 3 or parts[0] != str(tenant_id) or not storage.valid_key(key):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        _own_job(session, tenant_id, driver, UUID(parts[1]))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip()
    if content_type not in storage.ALLOWED_TYPES or not key.endswith(storage.ALLOWED_TYPES[content_type]):
        raise HTTPException(status_code=415, detail="Only JPEG, PNG or WebP images are accepted")
    body = await request.body()
    if not body or len(body) > storage.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Image must be between 1 byte and {storage.MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    storage.local_storage().put(key, body)
    return {"object_url": f"media://{key}", "bytes": len(body)}


class PushKeys(SQLModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=4, max_length=100)


class PushSubscribe(SQLModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(min_length=10, max_length=1000)
    keys: PushKeys


class PushUnsubscribe(SQLModel):
    endpoint: str = Field(min_length=10, max_length=1000)


@router.get("/push/key")
def push_key(tenant_id: UUID, driver: Driver = Depends(driver_principal)) -> dict:
    """The public key the phone needs to subscribe. Null when alerts are not set up on the server."""
    from routebridge.services.push import push_enabled

    return {"public_key": get_settings().vapid_public_key if push_enabled() else None}


@router.post("/push/subscribe", status_code=201)
def push_subscribe(tenant_id: UUID, payload: PushSubscribe, driver: Driver = Depends(driver_principal), session: Session = Depends(get_session)) -> dict:
    # the same phone re-subscribing replaces its old row, and a phone handed to another rider moves with the new sign-in
    existing = session.exec(select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)).first()
    if existing is not None:
        existing.tenant_id, existing.driver_id, existing.p256dh, existing.auth, existing.failures = tenant_id, driver.id, payload.keys.p256dh, payload.keys.auth, 0
        session.add(existing)
    else:
        session.add(PushSubscription(tenant_id=tenant_id, driver_id=driver.id, endpoint=payload.endpoint, p256dh=payload.keys.p256dh, auth=payload.keys.auth))
    session.commit()
    return {"subscribed": True}


@router.post("/push/unsubscribe")
def push_unsubscribe(tenant_id: UUID, payload: PushUnsubscribe, driver: Driver = Depends(driver_principal), session: Session = Depends(get_session)) -> dict:
    existing = session.exec(select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint, PushSubscription.driver_id == driver.id)).first()
    if existing is not None:
        session.delete(existing)
        session.commit()
    return {"subscribed": False}
