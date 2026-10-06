from fastapi.testclient import TestClient
from sqlmodel import Session

from routebridge.db.session import create_db_and_tables, engine
from routebridge.main import app
from routebridge.models.core import Tenant
from routebridge.models.operations import Driver, DriverAssignment
from routebridge.models.orders import Customer, DeliveryJob, Merchant, Order, Stop

client = TestClient(app)
create_db_and_tables()


def _seed() -> tuple:
    with Session(engine) as session:
        tenant = Tenant(name="Contract Tenant")
        session.add(tenant)
        session.flush()
        merchant = Merchant(tenant_id=tenant.id, name="Contract Merchant")
        customer = Customer(tenant_id=tenant.id, name="Ada Okafor", phone="+2348000000000")
        session.add_all([merchant, customer])
        session.flush()
        order = Order(tenant_id=tenant.id, merchant_id=merchant.id, customer_id=customer.id, external_ref="C-1", cod_amount=4500)
        session.add(order)
        session.flush()
        job = DeliveryJob(tenant_id=tenant.id, order_id=order.id, status="assigned")
        session.add(job)
        session.flush()
        session.add(Stop(tenant_id=tenant.id, delivery_job_id=job.id, address_text="Ikeja", landmark="Near gate"))
        driver = Driver(tenant_id=tenant.id, name="Musa Bello", phone="+2348111111111")
        session.add(driver)
        session.flush()
        session.add(DriverAssignment(tenant_id=tenant.id, delivery_job_id=job.id, driver_id=driver.id))
        orphan = Order(tenant_id=tenant.id, merchant_id=merchant.id, customer_id=customer.id, external_ref="C-2")
        session.add(orphan)
        session.commit()
        return tenant.id


def test_orders_list_is_enriched_and_keeps_orders_without_jobs() -> None:
    tenant_id = _seed()
    rows = client.get(f"/api/v1/tenants/{tenant_id}/orders").json()
    by_ref = {r["external_ref"]: r for r in rows}
    full = by_ref["C-1"]
    assert full["customer_name"] == "Ada Okafor"
    assert full["merchant_name"] == "Contract Merchant"
    assert full["job_status"] == "assigned"
    assert full["driver_name"] == "Musa Bello"
    assert full["address_text"] == "Ikeja"
    assert isinstance(full["cod_amount"], str)  # decimals are serialized as strings
    assert by_ref["C-2"]["delivery_job_id"] is None


def test_drivers_and_my_tenants_endpoints() -> None:
    tenant_id = _seed()
    drivers = client.get(f"/api/v1/tenants/{tenant_id}/drivers")
    assert drivers.status_code == 200 and drivers.json()[0]["name"] == "Musa Bello"
    mine = client.get("/api/v1/auth/me/tenants", headers={"Authorization": "Bearer not-checked-in-dev"})
    assert mine.status_code == 200
    assert str(tenant_id) in {t["tenant_id"] for t in mine.json()}


def test_dev_mode_ignores_bearer_when_clerk_unconfigured() -> None:
    tenant_id = _seed()
    response = client.get(f"/api/v1/tenants/{tenant_id}/orders", headers={"Authorization": "Bearer anything"})
    assert response.status_code == 200


def test_merchants_list_and_notification_recipient() -> None:
    tenant_id = _seed()
    merchants = client.get(f"/api/v1/tenants/{tenant_id}/merchants")
    assert merchants.status_code == 200 and merchants.json()[0]["name"] == "Contract Merchant"
    order_id = client.get(f"/api/v1/tenants/{tenant_id}/orders").json()[0]["id"]
    queued = client.post(f"/api/v1/tenants/{tenant_id}/orders/{order_id}/notifications", params={"channel": "sms", "template": "order_confirmed"})
    assert queued.status_code == 201
    assert queued.json()["recipient"] == "+2348000000000"


def test_tenant_creation_requires_platform_admin() -> None:
    from routebridge.auth.dependencies import get_optional_user
    from routebridge.config.settings import get_settings
    from routebridge.integrations.clerk import ClerkUser

    app.dependency_overrides[get_optional_user] = lambda: ClerkUser("user_not_admin", {})
    try:
        denied = client.post("/api/v1/admin/tenants", json={"name": "Nope"})
        assert denied.status_code == 403
        get_settings().platform_admin_subjects.append("user_not_admin")
        allowed = client.post("/api/v1/admin/tenants", json={"name": "Yes"})
        assert allowed.status_code == 201
    finally:
        get_settings().platform_admin_subjects.clear()
        app.dependency_overrides.pop(get_optional_user, None)
