"""Closeout and learning: KPIs, exception queue, partner payout export, statement reconciliation."""
import csv
import io
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlmodel import Session, select

from routebridge.auth.authorization import tenant_member, tenant_roles
from routebridge.db.session import get_session
from routebridge.models.catalog import RateCard, ServiceZone
from routebridge.models.core import utc_now
from routebridge.models.operations import DeliveryAttempt, Driver, DriverAssignment, PaymentRecord, ReconciliationItem
from routebridge.models.orders import DeliveryJob, Merchant, Order
from routebridge.models.plans import JobPlan
from routebridge.routes.operations import require_tenant
from routebridge.routes.orders import to_order_reads
from routebridge.services.events import record_event
from routebridge.services.statements import build_statement, statement_csv

FINANCE_ROLES = ("tenant_owner", "tenant_admin", "operations_manager", "finance")
router = APIRouter(prefix="/tenants/{tenant_id}", tags=["reports"], dependencies=[Depends(tenant_member)])


def _aware(value: datetime | None) -> datetime | None:
    return None if value is None else value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _rate_for_zone(session: Session, tenant_id: UUID) -> dict[UUID | None, Decimal]:
    rates: dict[UUID | None, Decimal] = {}
    for card in session.exec(select(RateCard).where(RateCard.tenant_id == tenant_id, RateCard.status == "active").order_by(RateCard.created_at)).all():
        rates.setdefault(card.service_zone_id, card.base_amount)
    return rates


@router.get("/reports/summary")
def summary(tenant_id: UUID, days: int = Query(default=30, ge=1, le=365), session: Session = Depends(get_session)) -> dict:
    require_tenant(session, tenant_id)
    since = utc_now() - timedelta(days=days)
    jobs = session.exec(select(DeliveryJob).where(DeliveryJob.tenant_id == tenant_id, DeliveryJob.created_at >= since)).all()
    job_ids = [j.id for j in jobs]
    delivered = [j for j in jobs if j.status == "delivered"]
    plans = {p.delivery_job_id: p for p in session.exec(select(JobPlan).where(JobPlan.delivery_job_id.in_(job_ids))).all()} if job_ids else {}
    attempts = session.exec(select(DeliveryAttempt).where(DeliveryAttempt.delivery_job_id.in_(job_ids))).all() if job_ids else []
    failed_by_job: dict[UUID, int] = Counter(a.delivery_job_id for a in attempts if a.status in {"failed_attempt", "rescheduled", "returned"})

    windowed = [j for j in delivered if plans.get(j.id) and plans[j.id].window_end]
    on_time = sum(1 for j in windowed if _aware(j.updated_at) <= _aware(plans[j.id].window_end))
    first_attempt = sum(1 for j in delivered if failed_by_job.get(j.id, 0) == 0)

    zones = {z.id: z.name for z in session.exec(select(ServiceZone).where(ServiceZone.tenant_id == tenant_id)).all()}
    reasons: Counter = Counter()
    job_zone = {j.id: (plans[j.id].service_zone_id if j.id in plans else None) for j in jobs}
    for a in attempts:
        if a.status in {"failed_attempt", "rescheduled", "returned"}:
            reasons[(job_zone.get(a.delivery_job_id), a.reason_code or "unspecified")] += 1

    payments = session.exec(select(PaymentRecord).where(PaymentRecord.tenant_id == tenant_id, PaymentRecord.recorded_at >= since)).all()
    open_items = session.exec(select(ReconciliationItem).where(ReconciliationItem.tenant_id == tenant_id, ReconciliationItem.status == "open")).all()

    rates = _rate_for_zone(session, tenant_id)
    cost = sum((rates.get(job_zone.get(j.id), Decimal("0")) for j in delivered), Decimal("0"))
    assignments = session.exec(select(DriverAssignment).where(DriverAssignment.delivery_job_id.in_([j.id for j in delivered]))).all() if delivered else []
    drivers_used = {a.driver_id for a in assignments}

    def rate(n: int, d: int) -> float | None:
        return round(n / d, 4) if d else None

    return {
        "period_days": days,
        "jobs_total": len(jobs),
        "jobs_delivered": len(delivered),
        "jobs_failed_or_returned": sum(1 for j in jobs if j.status in {"failed_attempt", "returned", "cancelled"}),
        "on_time_rate": rate(on_time, len(windowed)),
        "on_time_sample": len(windowed),
        "first_attempt_success_rate": rate(first_attempt, len(delivered)),
        "failure_reasons": sorted(
            ({"service_zone_id": z, "zone_name": zones.get(z), "reason_code": r, "count": c} for (z, r), c in reasons.items()),
            key=lambda row: -row["count"],
        ),
        "cod": {
            "expected": str(sum((p.expected_amount for p in payments), Decimal("0"))),
            "collected": str(sum((p.collected_amount for p in payments), Decimal("0"))),
            "open_reconciliation_items": len(open_items),
            "open_variance": str(sum((abs(i.variance_amount) for i in open_items), Decimal("0"))),
        },
        "cost_per_stop": str((cost / len(delivered)).quantize(Decimal("0.01"))) if delivered and cost else None,
        "stops_per_driver": round(len(delivered) / len(drivers_used), 2) if drivers_used else None,
    }


@router.get("/exceptions")
def exception_queue(tenant_id: UUID, session: Session = Depends(get_session)) -> list[dict]:
    """Everything that needs a human: failed deliveries, late/unassigned jobs, weak locations, COD variances."""
    require_tenant(session, tenant_id)
    now = utc_now()
    orders = session.exec(select(Order).where(Order.tenant_id == tenant_id).order_by(Order.created_at.desc()).limit(500)).all()
    items: list[dict] = []
    attempts_by_job: dict[UUID, DeliveryAttempt] = {}
    for read in to_order_reads(session, list(orders)):
        if read.delivery_job_id is None:
            items.append({"kind": "no_delivery_job", "severity": "high", "order_id": read.id, "job_id": None, "external_ref": read.external_ref, "detail": "Order has no delivery job", "since": read.created_at})
            continue
        status = read.job_status or "pending"
        if status in {"delivered", "cancelled"}:
            continue
        base = {"order_id": read.id, "job_id": read.delivery_job_id, "external_ref": read.external_ref}
        if status in {"failed_attempt", "returned"}:
            if read.delivery_job_id not in attempts_by_job:
                last = session.exec(select(DeliveryAttempt).where(DeliveryAttempt.delivery_job_id == read.delivery_job_id).order_by(DeliveryAttempt.attempt_number.desc())).first()
                if last:
                    attempts_by_job[read.delivery_job_id] = last
            last = attempts_by_job.get(read.delivery_job_id)
            items.append({**base, "kind": "delivery_failed", "severity": "high", "detail": f"{status.replace('_', ' ')}: {last.reason_code if last and last.reason_code else 'no reason recorded'}", "since": last.occurred_at if last else read.created_at})
        end = _aware(read.window_end)
        if end and end < now:
            items.append({**base, "kind": "late", "severity": "high", "detail": "Delivery window has passed", "since": end})
        elif status == "pending" and end and end < now + timedelta(hours=1):
            items.append({**base, "kind": "unassigned_soon", "severity": "medium", "detail": "No driver assigned and the window closes within an hour", "since": read.created_at})
        if read.location_score is not None and read.location_score < 45:
            items.append({**base, "kind": "low_location_confidence", "severity": "medium", "detail": f"Location score {read.location_score}/100; confirm with customer", "since": read.created_at})
    for item in session.exec(select(ReconciliationItem).where(ReconciliationItem.tenant_id == tenant_id, ReconciliationItem.status == "open")).all():
        items.append({"kind": "cod_variance", "severity": "high", "order_id": None, "job_id": None, "external_ref": None, "detail": f"COD variance of {item.variance_amount}", "since": item.created_at, "reconciliation_item_id": item.id})
    return sorted(items, key=lambda i: (0 if i["severity"] == "high" else 1, str(i["since"])))


@router.get("/payouts/export", dependencies=[Depends(tenant_roles(*FINANCE_ROLES))])
def export_payouts(tenant_id: UUID, start: datetime = Query(alias="from"), end: datetime = Query(alias="to"), session: Session = Depends(get_session)) -> Response:
    """CSV of per-driver/partner payout totals for jobs delivered in [from, to). Amounts come from zone rate cards."""
    require_tenant(session, tenant_id)
    if end <= start:
        raise HTTPException(status_code=422, detail="'to' must be after 'from'")
    start_naive, end_naive = _aware(start).replace(tzinfo=None), _aware(end).replace(tzinfo=None)
    jobs = [j for j in session.exec(select(DeliveryJob).where(DeliveryJob.tenant_id == tenant_id, DeliveryJob.status == "delivered")).all() if start_naive <= _aware(j.updated_at).replace(tzinfo=None) < end_naive]
    rates = _rate_for_zone(session, tenant_id)
    plans = {p.delivery_job_id: p for p in session.exec(select(JobPlan).where(JobPlan.delivery_job_id.in_([j.id for j in jobs]))).all()} if jobs else {}
    assignments = {}
    if jobs:
        for a in session.exec(select(DriverAssignment).where(DriverAssignment.delivery_job_id.in_([j.id for j in jobs])).order_by(DriverAssignment.assigned_at)).all():
            assignments[a.delivery_job_id] = a
    payments = {p.delivery_job_id: p for p in session.exec(select(PaymentRecord).where(PaymentRecord.delivery_job_id.in_([j.id for j in jobs]))).all()} if jobs else {}
    drivers = {d.id: d for d in session.exec(select(Driver).where(Driver.tenant_id == tenant_id)).all()}
    totals: dict[UUID | None, dict] = defaultdict(lambda: {"jobs": 0, "cod": Decimal("0"), "amount": Decimal("0")})
    for job in jobs:
        assignment = assignments.get(job.id)
        row = totals[assignment.driver_id if assignment else None]
        row["jobs"] += 1
        row["amount"] += rates.get(plans[job.id].service_zone_id if job.id in plans else None, Decimal("0"))
        if job.id in payments:
            row["cod"] += payments[job.id].collected_amount
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["driver_id", "driver_name", "fleet_type", "jobs_delivered", "cod_collected", "payout_amount", "currency"])
    for driver_id, row in sorted(totals.items(), key=lambda kv: str(kv[0])):
        driver = drivers.get(driver_id)
        writer.writerow([driver_id or "", driver.name if driver else "unassigned", driver.fleet_type if driver else "", row["jobs"], row["cod"], row["amount"], "NGN"])
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=payouts.csv"})


MAX_STATEMENT_BYTES = 5 * 1024 * 1024


@router.post("/reconciliation/import-statement", dependencies=[Depends(tenant_roles(*FINANCE_ROLES))])
def import_statement(tenant_id: UUID, file: UploadFile = File(...), session: Session = Depends(get_session)) -> dict:
    """Dual reconciliation: match a gateway/bank statement CSV (columns: reference, amount) to recorded payments.

    A mismatch opens a ReconciliationItem; unknown references are returned for manual review. Matching a payment
    never auto-resolves an existing driver-side variance.
    """
    require_tenant(session, tenant_id)
    raw = file.file.read(MAX_STATEMENT_BYTES + 1)
    if len(raw) > MAX_STATEMENT_BYTES:
        raise HTTPException(status_code=413, detail="Statement exceeds 5 MB limit")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc
    if not reader.fieldnames or not {"reference", "amount"} <= {f.strip().lower() for f in reader.fieldnames}:
        raise HTTPException(status_code=400, detail={"missing_columns": ["reference", "amount"]})
    matched, mismatched, unmatched, invalid = 0, 0, [], []
    for number, row in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        try:
            amount = Decimal(row["amount"].replace(",", ""))
        except Exception:
            invalid.append({"row": number, "reference": row.get("reference"), "reason": "invalid amount"})
            continue
        payment = session.exec(select(PaymentRecord).where(PaymentRecord.tenant_id == tenant_id, PaymentRecord.provider_reference == row["reference"])).first()
        if payment is None:
            unmatched.append({"row": number, "reference": row["reference"], "amount": str(amount)})
        elif amount == payment.collected_amount:
            matched += 1
            if payment.reconciliation_status == "pending":
                payment.reconciliation_status = "matched"
        else:
            mismatched += 1
            existing = session.exec(select(ReconciliationItem).where(ReconciliationItem.payment_id == payment.id, ReconciliationItem.status == "open")).first()
            if existing is None:
                payment.reconciliation_status = "exception"
                session.add(ReconciliationItem(tenant_id=tenant_id, payment_id=payment.id, variance_amount=amount - payment.collected_amount))
    record_event(session, tenant_id, "reconciliation.statement_imported", "tenant", tenant_id, {"matched": matched, "mismatched": mismatched, "unmatched": len(unmatched)})
    session.commit()
    return {"matched": matched, "mismatched": mismatched, "unmatched": unmatched, "invalid_rows": invalid}


def _statement_for(session: Session, tenant_id: UUID, merchant_id: UUID, start: datetime, end: datetime) -> dict:
    merchant = session.get(Merchant, merchant_id)
    if merchant is None or merchant.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Merchant not found")
    if end <= start:
        raise HTTPException(status_code=422, detail="'to' must be after 'from'")
    return build_statement(session, tenant_id, merchant, start, end)


@router.get("/merchants/{merchant_id}/statement", dependencies=[Depends(tenant_roles(*FINANCE_ROLES))])
def merchant_statement(tenant_id: UUID, merchant_id: UUID, start: datetime = Query(alias="from"), end: datetime = Query(alias="to"), session: Session = Depends(get_session)) -> dict:
    """What was delivered for one shop in a period, the cash collected, the delivery fees and the net to pay the shop."""
    return jsonable_encoder(_statement_for(session, tenant_id, merchant_id, start, end))


@router.get("/merchants/{merchant_id}/statement.csv", dependencies=[Depends(tenant_roles(*FINANCE_ROLES))])
def merchant_statement_csv(tenant_id: UUID, merchant_id: UUID, start: datetime = Query(alias="from"), end: datetime = Query(alias="to"), session: Session = Depends(get_session)) -> Response:
    statement = _statement_for(session, tenant_id, merchant_id, start, end)
    return Response(statement_csv(statement), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=statement.csv"})
