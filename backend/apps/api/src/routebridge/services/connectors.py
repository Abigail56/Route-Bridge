"""Map storefront webhook payloads (Shopify, WooCommerce, generic) to the canonical OrderCreate."""
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from routebridge.models.orders import OrderCreate


class ConnectorError(ValueError):
    pass


def _money(value: Any) -> Decimal:
    try:
        return max(Decimal(str(value or "0")), Decimal("0")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise ConnectorError(f"Invalid amount: {value!r}") from exc


def _join(*parts: Any) -> str:
    return ", ".join(str(p).strip() for p in parts if p and str(p).strip())


def _require(value: str, label: str) -> str:
    if not value or not value.strip():
        raise ConnectorError(f"Missing {label}")
    return value.strip()


def from_shopify(payload: dict, merchant_id: UUID) -> OrderCreate:
    ship = payload.get("shipping_address") or {}
    customer = payload.get("customer") or {}
    name = ship.get("name") or _join(customer.get("first_name"), customer.get("last_name")).replace(", ", " ")
    gateways = " ".join(payload.get("payment_gateway_names") or [payload.get("gateway") or ""]).lower()
    is_cod = "cod" in gateways or "cash on delivery" in gateways or payload.get("financial_status") == "pending"
    total = _money(payload.get("total_price"))
    return OrderCreate(
        merchant_id=merchant_id,
        customer_name=_require(name, "customer name"),
        customer_phone=_require(ship.get("phone") or customer.get("phone") or payload.get("phone") or "", "customer phone"),
        external_ref=_require(str(payload.get("name") or payload.get("id") or ""), "order reference"),
        currency=(payload.get("currency") or "NGN").upper(),
        total_amount=total,
        cod_amount=total if is_cod else Decimal("0.00"),
        address_text=_require(_join(ship.get("address1"), ship.get("address2"), ship.get("city"), ship.get("province")), "shipping address"),
        delivery_notes=(payload.get("note") or None),
        latitude=ship.get("latitude"),
        longitude=ship.get("longitude"),
    )


def from_woocommerce(payload: dict, merchant_id: UUID) -> OrderCreate:
    ship = payload.get("shipping") or {}
    bill = payload.get("billing") or {}
    name = _join(ship.get("first_name") or bill.get("first_name"), ship.get("last_name") or bill.get("last_name")).replace(", ", " ")
    total = _money(payload.get("total"))
    return OrderCreate(
        merchant_id=merchant_id,
        customer_name=_require(name, "customer name"),
        customer_phone=_require(ship.get("phone") or bill.get("phone") or "", "customer phone"),
        external_ref=_require(str(payload.get("number") or payload.get("id") or ""), "order reference"),
        currency=(payload.get("currency") or "NGN").upper(),
        total_amount=total,
        cod_amount=total if payload.get("payment_method") == "cod" else Decimal("0.00"),
        address_text=_require(_join(ship.get("address_1") or bill.get("address_1"), ship.get("address_2") or bill.get("address_2"), ship.get("city") or bill.get("city"), ship.get("state") or bill.get("state")), "shipping address"),
        delivery_notes=(payload.get("customer_note") or None),
    )


def from_generic(payload: dict, merchant_id: UUID) -> OrderCreate:
    return OrderCreate(**{**payload, "merchant_id": merchant_id})


CONNECTORS = {"shopify": from_shopify, "woocommerce": from_woocommerce, "generic": from_generic}
