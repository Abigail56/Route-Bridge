"""Merchant payout statements: for one shop and a date range, what was delivered, the cash collected, RouteBridge's delivery fees and what is left to pay the shop.

Fees come from the workspace's active rate card for the order's zone (base fee, plus the COD fee when cash was due). Cash collected is what the rider
recorded; a delivered cash order with no recorded payment counts as 0 collected and is flagged so finance can chase it.
"""
import csv
import io
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session, select

from routebridge.models.catalog import RateCard
from routebridge.models.claims import Claim
from routebridge.models.operations import PaymentRecord
from routebridge.models.orders import Customer, DeliveryJob, Merchant, Order
from routebridge.models.plans import JobPlan

ZERO = Decimal("0.00")


def _naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def build_statement(session: Session, tenant_id: UUID, merchant: Merchant, start: datetime, end: datetime) -> dict:
    start_n, end_n = _naive(start), _naive(end)
    rows = session.exec(select(DeliveryJob, Order).join(Order, Order.id == DeliveryJob.order_id).where(DeliveryJob.tenant_id == tenant_id, Order.merchant_id == merchant.id, DeliveryJob.status == "delivered")).all()
    delivered = [(job, order) for job, order in rows if start_n <= _naive(job.updated_at) < end_n]
    job_ids = [job.id for job, _ in delivered]
    plans = {p.delivery_job_id: p for p in session.exec(select(JobPlan).where(JobPlan.delivery_job_id.in_(job_ids))).all()} if job_ids else {}
    payments = {p.delivery_job_id: p for p in session.exec(select(PaymentRecord).where(PaymentRecord.delivery_job_id.in_(job_ids))).all()} if job_ids else {}
    customers = {c.id: c for c in session.exec(select(Customer).where(Customer.id.in_([o.customer_id for _, o in delivered]))).all()} if delivered else {}
    cards: dict[UUID | None, RateCard] = {}
    for card in session.exec(select(RateCard).where(RateCard.tenant_id == tenant_id, RateCard.status == "active").order_by(RateCard.created_at)).all():
        cards.setdefault(card.service_zone_id, card)

    lines = []
    for job, order in sorted(delivered, key=lambda pair: _naive(pair[0].updated_at)):
        plan = plans.get(job.id)
        card = cards.get(plan.service_zone_id if plan else None)
        payment = payments.get(job.id)
        cod_due = order.cod_amount > 0
        collected = payment.collected_amount if payment else ZERO
        fee = (card.base_amount + (card.cod_fee if cod_due else ZERO)) if card else ZERO
        note = ""
        if cod_due and payment is None:
            note = "Cash not recorded"
        elif cod_due and payment and payment.collected_amount != order.cod_amount:
            note = "Cash differs from the amount due"
        elif card is None:
            note = "No rate card for this zone"
        customer = customers.get(order.customer_id)
        lines.append({"order_ref": order.external_ref, "delivered_at": job.updated_at, "customer": customer.name if customer else "", "cod_due": order.cod_amount, "cash_collected": collected, "delivery_fee": fee, "note": note})
    approved = session.exec(select(Claim).where(Claim.tenant_id == tenant_id, Claim.merchant_id == merchant.id, Claim.status.in_(("approved", "paid")), Claim.raised_by == "merchant")).all()
    credits = [{"kind": c.kind, "description": c.description, "amount": c.amount_approved or ZERO, "decided_at": c.decided_at} for c in approved if c.decided_at and start_n <= _naive(c.decided_at) < end_n]
    credits_total = sum((c["amount"] for c in credits), ZERO)
    collected_total = sum((l["cash_collected"] for l in lines), ZERO)
    fees_total = sum((l["delivery_fee"] for l in lines), ZERO)
    return {
        "merchant_id": merchant.id, "merchant_name": merchant.name, "from": start, "to": end, "currency": "NGN",
        "deliveries": len(lines), "cash_collected": collected_total, "delivery_fees": fees_total,
        # cash we hold for the shop, minus the delivery fees, plus claims we approved in its favour (negative = the shop owes the company)
        "claim_credits": credits_total, "claims": credits,
        "net_payable": collected_total - fees_total + credits_total, "lines": lines,
    }


def statement_csv(statement: dict) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Merchant", statement["merchant_name"]])
    writer.writerow(["Period", f"{statement['from']:%Y-%m-%d} to {statement['to']:%Y-%m-%d}"])
    writer.writerow([])
    writer.writerow(["order_ref", "delivered_at", "customer", "cod_due", "cash_collected", "delivery_fee", "note"])
    for line in statement["lines"]:
        writer.writerow([_safe(line["order_ref"]), f"{line['delivered_at']:%Y-%m-%d %H:%M}", _safe(line["customer"]), line["cod_due"], line["cash_collected"], line["delivery_fee"], line["note"]])
    writer.writerow([])
    writer.writerow(["Deliveries", statement["deliveries"]])
    writer.writerow(["Cash collected", statement["cash_collected"]])
    writer.writerow(["Delivery fees", statement["delivery_fees"]])
    writer.writerow(["Approved claims (owed to merchant)", statement["claim_credits"]])
    writer.writerow(["Net payable to merchant", statement["net_payable"]])
    return out.getvalue()


def _safe(value: str) -> str:
    """Stop a customer-typed value from running as a spreadsheet formula when the CSV is opened."""
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value
