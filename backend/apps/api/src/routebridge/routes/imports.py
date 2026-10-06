import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session

from routebridge.routes.orders import create_order
from routebridge.db.session import get_session
from routebridge.models.orders import OrderCreate, OrderRead
from routebridge.auth.authorization import tenant_roles

MAX_CSV_BYTES = 10 * 1024 * 1024  # 10 MB

IMPORT_ROLES = ("tenant_owner", "tenant_admin", "dispatcher", "operations_manager")
router = APIRouter(prefix="/tenants/{tenant_id}/orders", tags=["order-import"], dependencies=[Depends(tenant_roles(*IMPORT_ROLES))])
REQUIRED = {"merchant_id", "customer_name", "customer_phone", "external_ref", "address_text"}


@router.post("/import-csv", response_model=list[OrderRead])
def import_orders_csv(
    tenant_id: UUID,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> list[OrderRead]:
    # Stream-read in chunks to prevent OOM on large uploads
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(64 * 1024)  # 64 KB at a time
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_CSV_BYTES:
            raise HTTPException(status_code=413, detail="CSV file exceeds 10 MB limit")
        chunks.append(chunk)
    raw = b"".join(chunks)

    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc
    if not reader.fieldnames or not REQUIRED.issubset(set(reader.fieldnames)):
        missing = sorted(REQUIRED - set(reader.fieldnames or []))
        raise HTTPException(status_code=400, detail={"missing_columns": missing})

    created: list[OrderRead] = []
    errors: list[dict] = []
    for row_number, row in enumerate(reader, start=2):
        # Use a savepoint so one bad row doesn't roll back the entire batch
        savepoint = session.begin_nested()
        try:
            payload = OrderCreate(
                merchant_id=UUID(row["merchant_id"]),
                customer_name=row["customer_name"],
                customer_phone=row["customer_phone"],
                external_ref=row["external_ref"],
                currency=row.get("currency") or "NGN",
                total_amount=row.get("total_amount") or "0",
                cod_amount=row.get("cod_amount") or "0",
                address_text=row["address_text"],
                landmark=row.get("landmark") or None,
                delivery_notes=row.get("delivery_notes") or None,
                latitude=float(row["latitude"]) if row.get("latitude") else None,
                longitude=float(row["longitude"]) if row.get("longitude") else None,
                location_confidence=row.get("location_confidence") or "unverified",
                plus_code=row.get("plus_code") or None,
                recipient_available={"true": True, "yes": True, "1": True, "false": False, "no": False, "0": False}.get((row.get("recipient_available") or "").strip().lower()),
                service_zone_id=UUID(row["service_zone_id"]) if row.get("service_zone_id") else None,
                window_start=row.get("window_start") or None,
                window_end=row.get("window_end") or None,
            )
            created.append(create_order(tenant_id, payload, None, session))
            savepoint.commit()
        except Exception as exc:  # row-level validation must not hide the row number
            savepoint.rollback()
            errors.append({"row": row_number, "error": str(exc)})
    if errors:
        raise HTTPException(status_code=422, detail={"created_count": len(created), "errors": errors})
    session.commit()
    return created
