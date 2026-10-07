from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.auth.dependencies import get_optional_user
from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.integrations.clerk import ClerkUser
from routebridge.main import app
from routebridge.models.catalog import RateCard, ServiceZone
from routebridge.models.core import Country, OperatingArea, Tenant, utc_now
from routebridge.models.operations import PaymentRecord
from routebridge.models.orders import Customer, DeliveryJob, Merchant, Order
from routebridge.models.plans import JobPlan

client = TestClient(app)
create_db_and_tables()


@pytest.fixture
def as_user():
    settings = get_settings()
    old = (settings.require_clerk_auth, list(settings.platform_admin_subjects))
    settings.require_clerk_auth = True

    def sign_in(subject: str, listed_admin: bool = False):
        app.dependency_overrides[get_optional_user] = lambda: ClerkUser(subject, {"email": f"{subject}@example.test"})
        settings.platform_admin_subjects[:] = [subject] if listed_admin else []

    yield sign_in
    app.dependency_overrides.pop(get_optional_user, None)
    settings.require_clerk_auth = old[0]
    settings.platform_admin_subjects[:] = old[1]


def _id() -> str:
    return f"user_{uuid4().hex[:12]}"


def delivered(session, tenant, merchant, zone, ref, cod, collected, customer_name="Ada") -> None:
    customer = Customer(tenant_id=tenant.id, name=customer_name, phone="+2348011111111")
    session.add(customer)
    session.flush()
    order = Order(tenant_id=tenant.id, merchant_id=merchant.id, customer_id=customer.id, external_ref=ref, cod_amount=Decimal(cod), total_amount=Decimal(cod))
    session.add(order)
    session.flush()
    job = DeliveryJob(tenant_id=tenant.id, order_id=order.id, status="delivered")
    session.add(job)
    session.flush()
    session.add(JobPlan(tenant_id=tenant.id, delivery_job_id=job.id, service_zone_id=zone.id))
    if collected is not None:
        session.add(PaymentRecord(tenant_id=tenant.id, order_id=order.id, delivery_job_id=job.id, expected_amount=Decimal(cod), collected_amount=Decimal(collected)))


@pytest.fixture
def company(as_user):
    with Session(engine) as session:
        country = session.exec(select(Country)).first() or Country(iso_code="NG", name="Nigeria")
        session.add(country)
        session.flush()
        area = OperatingArea(country_id=country.id, code=f"A{uuid4().hex[:6]}", name="Test area")
        tenant = Tenant(name="Statement Logistics")
        session.add_all([area, tenant])
        session.flush()
        zone = ServiceZone(tenant_id=tenant.id, operating_area_id=area.id, code="Z1", name="Zone 1")
        shop_a, shop_b = Merchant(tenant_id=tenant.id, name="Shop A"), Merchant(tenant_id=tenant.id, name="Shop B")
        session.add_all([zone, shop_a, shop_b])
        session.flush()
        session.add(RateCard(tenant_id=tenant.id, service_zone_id=zone.id, name="Std", base_amount=Decimal("1500"), cod_fee=Decimal("200")))
        delivered(session, tenant, shop_a, zone, "A-1", "10000", "10000", customer_name="=cmd|' /C calc'!A0")
        delivered(session, tenant, shop_a, zone, "A-2", "0", None)  # prepaid: fee only
        delivered(session, tenant, shop_a, zone, "A-3", "5000", None)  # cash never recorded
        delivered(session, tenant, shop_b, zone, "B-1", "7000", "7000")
        session.commit()
        ids = {"tenant": str(tenant.id), "a": str(shop_a.id), "b": str(shop_b.id)}
    people = {"owner": _id(), "a": _id(), "b": _id(), "boss": _id(), "dispatcher": _id()}
    as_user(people["boss"], listed_admin=True)
    t = ids["tenant"]
    client.post(f"/api/v1/platform/tenants/{t}/owner", json={"clerk_user_id": people["owner"]})
    client.post(f"/api/v1/platform/tenants/{t}/members", json={"clerk_user_id": people["a"], "role": "merchant_user", "merchant_id": ids["a"]})
    client.post(f"/api/v1/platform/tenants/{t}/members", json={"clerk_user_id": people["b"], "role": "merchant_user", "merchant_id": ids["b"]})
    client.post(f"/api/v1/platform/tenants/{t}/members", json={"clerk_user_id": people["dispatcher"], "role": "dispatcher"})
    as_user(people["owner"])
    return {**ids, "people": people}


def window() -> dict:
    return {"from": (utc_now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"), "to": (utc_now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")}


def test_a_statement_adds_cash_and_subtracts_fees(company) -> None:
    body = client.get(f"/api/v1/tenants/{company['tenant']}/merchants/{company['a']}/statement", params=window()).json()
    assert body["merchant_name"] == "Shop A" and body["deliveries"] == 3
    assert Decimal(body["cash_collected"]) == Decimal("10000")
    # A-1 cash order: 1500 + 200 cod fee. A-2 prepaid: 1500. A-3 cash order: 1700
    assert Decimal(body["delivery_fees"]) == Decimal("4900")
    assert Decimal(body["net_payable"]) == Decimal("5100")
    notes = {line["order_ref"]: line["note"] for line in body["lines"]}
    assert notes["A-3"] == "Cash not recorded" and notes["A-1"] == "" and notes["A-2"] == ""


def test_a_statement_only_counts_the_period_and_that_shop(company) -> None:
    old = {"from": (utc_now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"), "to": (utc_now() - timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert client.get(f"/api/v1/tenants/{company['tenant']}/merchants/{company['a']}/statement", params=old).json()["deliveries"] == 0
    assert client.get(f"/api/v1/tenants/{company['tenant']}/merchants/{company['b']}/statement", params=window()).json()["deliveries"] == 1
    assert client.get(f"/api/v1/tenants/{company['tenant']}/merchants/{company['a']}/statement", params={"from": window()["to"], "to": window()["from"]}).status_code == 422
    assert client.get(f"/api/v1/tenants/{company['tenant']}/merchants/{uuid4()}/statement", params=window()).status_code == 404


def test_csv_neutralises_spreadsheet_formulas(company) -> None:
    res = client.get(f"/api/v1/tenants/{company['tenant']}/merchants/{company['a']}/statement.csv", params=window())
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    assert "Net payable to merchant,5100" in res.text
    assert ",=cmd" not in res.text and "'=cmd" in res.text


def test_merchants_get_only_their_own_statement(company, as_user) -> None:
    as_user(company["people"]["b"])
    mine = client.get(f"/api/v1/tenants/{company['tenant']}/portal/statement", params=window()).json()
    assert mine["merchant_name"] == "Shop B" and mine["deliveries"] == 1 and Decimal(mine["net_payable"]) == Decimal("5300")
    # the staff route, which could name another shop, is closed to merchant accounts
    assert client.get(f"/api/v1/tenants/{company['tenant']}/merchants/{company['a']}/statement", params=window()).status_code == 403
    assert client.get(f"/api/v1/tenants/{company['tenant']}/portal/statement.csv", params=window()).status_code == 200


def test_staff_without_finance_access_cannot_read_statements(company, as_user) -> None:
    as_user(company["people"]["dispatcher"])
    assert client.get(f"/api/v1/tenants/{company['tenant']}/merchants/{company['a']}/statement", params=window()).status_code == 403
