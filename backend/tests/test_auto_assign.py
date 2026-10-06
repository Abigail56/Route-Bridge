from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.auth.dependencies import get_optional_user
from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.integrations.clerk import ClerkUser
from routebridge.main import app
from routebridge.models.core import Tenant
from routebridge.models.operations import Driver
from routebridge.models.orders import Merchant

client = TestClient(app)
create_db_and_tables()

# Lagos Island and a few points around it
IKEJA = (6.6018, 3.3515)
YABA = (6.5095, 3.3711)
SURULERE = (6.5003, 3.3500)
KANO = (12.0022, 8.5920)  # far away from every Lagos rider


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


@pytest.fixture
def company(as_user):
    with Session(engine) as session:
        tenant = Tenant(name="Auto Assign Logistics")
        session.add(tenant)
        session.flush()
        merchant = Merchant(tenant_id=tenant.id, name="Shop")
        session.add(merchant)
        session.commit()
        ids = {"tenant": str(tenant.id), "merchant": str(merchant.id)}
    owner, dispatcher, boss = (f"user_{uuid4().hex[:12]}" for _ in range(3))
    as_user(boss, listed_admin=True)
    t = ids["tenant"]
    client.post(f"/api/v1/platform/tenants/{t}/owner", json={"clerk_user_id": owner})
    client.post(f"/api/v1/platform/tenants/{t}/members", json={"clerk_user_id": dispatcher, "role": "dispatcher"})
    as_user(owner)
    return {**ids, "owner": owner, "dispatcher": dispatcher}


def driver(company, name, place=None, status="available") -> str:
    with Session(engine) as session:
        row = Driver(tenant_id=UUID(company["tenant"]), name=name, phone=f"+23480{uuid4().int % 10**8:08d}", status=status, latitude=place[0] if place else None, longitude=place[1] if place else None)
        session.add(row)
        session.commit()
        return str(row.id)


def order(company, place=None, ref=None) -> dict:
    body = {"merchant_id": company["merchant"], "customer_name": "Cust", "customer_phone": "+2348011111111", "external_ref": ref or f"R-{uuid4().hex[:8]}", "address_text": "somewhere"}
    if place:
        body["latitude"], body["longitude"] = place
    res = client.post(f"/api/v1/tenants/{company['tenant']}/orders", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def auto(company, job_id):
    return client.post(f"/api/v1/tenants/{company['tenant']}/delivery-jobs/{job_id}/auto-assign")


def test_the_nearest_available_driver_gets_the_job(company) -> None:
    near, far = driver(company, "Near Rider", YABA), driver(company, "Far Rider", SURULERE)
    job = order(company, place=IKEJA)["delivery_job_id"]
    res = auto(company, job).json()
    assert res["assigned"] and res["driver_id"] == near and res["method"] == "nearest" and 0 < res["distance_m"] < 15000
    listed = {d["id"]: d["status"] for d in client.get(f"/api/v1/tenants/{company['tenant']}/drivers").json()}
    assert listed[near] == "busy" and listed[far] == "available"
    assert order(company, place=IKEJA) and True  # a second job now goes to the next rider, because the first is busy
    second = [o for o in client.get(f"/api/v1/tenants/{company['tenant']}/orders").json() if o["job_status"] == "pending"][0]["delivery_job_id"]
    assert auto(company, second).json()["driver_id"] == far


def test_busy_and_offline_drivers_are_never_chosen(company) -> None:
    driver(company, "Busy Rider", IKEJA, status="busy")
    driver(company, "Offline Rider", IKEJA, status="offline")
    res = auto(company, order(company, place=IKEJA)["delivery_job_id"]).json()
    assert not res["assigned"] and res["reason"] == "no_available_driver"


def test_a_rider_too_far_away_is_not_sent(company) -> None:
    driver(company, "Lagos Rider", IKEJA)
    res = auto(company, order(company, place=KANO)["delivery_job_id"]).json()
    assert not res["assigned"] and res["reason"] == "no_driver_nearby"


def test_without_a_map_position_the_rider_idle_longest_gets_it(company) -> None:
    first, second = driver(company, "Aaa Rider"), driver(company, "Bbb Rider")
    one = auto(company, order(company)["delivery_job_id"]).json()
    assert one["assigned"] and one["method"] == "next_available" and one["driver_id"] == first  # nobody has worked yet: earliest name
    # the first rider finishes and is free again; the other one has now been idle longer, so they are next
    with Session(engine) as session:
        session.get(Driver, UUID(first)).status = "available"
        session.commit()
    two = auto(company, order(company)["delivery_job_id"]).json()
    assert two["driver_id"] == second


def test_orders_are_assigned_the_moment_they_are_created_when_the_company_turns_it_on(company, as_user) -> None:
    t = company["tenant"]
    near = driver(company, "Near Rider", YABA)
    assert client.get(f"/api/v1/tenants/{t}/dispatch/settings").json() == {"auto_assign": False}
    waiting = order(company, place=IKEJA)
    assert waiting["job_status"] == "pending" and waiting["driver_id"] is None  # off by default

    as_user(company["dispatcher"])  # only an owner or admin may switch it
    assert client.patch(f"/api/v1/tenants/{t}/dispatch/settings", json={"auto_assign": True}).status_code == 403
    as_user(company["owner"])
    assert client.patch(f"/api/v1/tenants/{t}/dispatch/settings", json={"auto_assign": True}).json() == {"auto_assign": True}

    free = driver(company, "Second Rider", SURULERE)
    created = order(company, place=IKEJA)
    assert created["job_status"] == "assigned" and created["driver_id"] in {near, free}
    # no rider left: the order is still created and simply waits
    leftover = order(company, place=IKEJA)
    assert leftover["job_status"] in {"assigned", "pending"}
    third = order(company, place=IKEJA)
    assert third["job_status"] == "pending" and third["driver_id"] is None


def test_assign_all_waiting_jobs_in_one_go(company) -> None:
    t = company["tenant"]
    a, b = driver(company, "Rider A", YABA), driver(company, "Rider B", SURULERE)
    jobs = [order(company, place=IKEJA)["delivery_job_id"] for _ in range(3)]
    res = client.post(f"/api/v1/tenants/{t}/dispatch/auto-assign").json()
    assert res["assigned"] == 2 and res["waiting"] == 1
    assert {r["driver_id"] for r in res["results"] if r["assigned"]} == {a, b}
    # a job that is already assigned is left alone
    assert auto(company, jobs[0]).json()["reason"] in {"not_waiting", "no_available_driver"}
    states = {o["delivery_job_id"]: o["job_status"] for o in client.get(f"/api/v1/tenants/{t}/orders").json()}
    assert sorted(states.values()).count("assigned") == 2 and sorted(states.values()).count("pending") == 1
