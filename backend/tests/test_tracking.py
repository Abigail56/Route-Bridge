from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from routebridge.auth.dependencies import get_optional_user
from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.integrations.clerk import ClerkUser
from routebridge.main import app
from routebridge.models.core import Tenant, utc_now
from routebridge.models.operations import Driver
from routebridge.models.orders import Merchant

client = TestClient(app)
create_db_and_tables()

IKEJA = (6.6018, 3.3515)
YABA = (6.5095, 3.3711)


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
        tenant = Tenant(name="Tracking Logistics")
        session.add(tenant)
        session.flush()
        shop = Merchant(tenant_id=tenant.id, name="Shop")
        session.add(shop)
        session.commit()
        ids = {"tenant": str(tenant.id), "merchant": str(shop.id)}
    owner, shop_user, boss = (f"user_{uuid4().hex[:12]}" for _ in range(3))
    as_user(boss, listed_admin=True)
    t = ids["tenant"]
    client.post(f"/api/v1/platform/tenants/{t}/owner", json={"clerk_user_id": owner})
    client.post(f"/api/v1/platform/tenants/{t}/members", json={"clerk_user_id": shop_user, "role": "merchant_user", "merchant_id": ids["merchant"]})
    as_user(owner)
    return {**ids, "owner": owner, "shop_user": shop_user}


def new_driver(company, place=None, seen_ago: timedelta | None = timedelta(seconds=20), name="Tracked Rider") -> str:
    with Session(engine) as session:
        row = Driver(tenant_id=UUID(company["tenant"]), name=name, phone=f"+23480{uuid4().int % 10**8:08d}", latitude=place[0] if place else None, longitude=place[1] if place else None,
                     last_location_at=(utc_now() - seen_ago) if (place and seen_ago is not None) else None)
        session.add(row)
        session.commit()
        return str(row.id)


def new_order(company, place=IKEJA) -> dict:
    body = {"merchant_id": company["merchant"], "customer_name": "Cust", "customer_phone": "+2348011111111", "external_ref": f"T-{uuid4().hex[:6]}", "address_text": "somewhere"}
    if place:
        body["latitude"], body["longitude"] = place
    res = client.post(f"/api/v1/tenants/{company['tenant']}/orders", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def move(company, job_id, *targets):
    for target in targets:
        res = client.post(f"/api/v1/tenants/{company['tenant']}/delivery-jobs/{job_id}/transitions", json={"target_status": target})
        assert res.status_code == 200, res.text


def customer_view(token: str) -> dict:
    res = client.get(f"/api/v1/public/tracking/{token}")
    assert res.status_code == 200, res.text
    return res.json()


def test_dispatchers_see_every_driver_their_delivery_and_an_estimate(company) -> None:
    t = company["tenant"]
    moving = new_driver(company, YABA, name="On The Road")
    stale = new_driver(company, YABA, seen_ago=timedelta(minutes=45), name="Gone Quiet")
    silent = new_driver(company, None, name="Never Reported")
    order = new_order(company)
    waiting = new_order(company)
    client.post(f"/api/v1/tenants/{t}/delivery-jobs/{order['delivery_job_id']}/assignments", json={"driver_id": moving})
    move(company, order["delivery_job_id"], "accepted", "en_route")

    view = client.get(f"/api/v1/tenants/{t}/tracking/drivers").json()
    by_name = {d["name"]: d for d in view["drivers"]}
    road = by_name["On The Road"]
    assert road["latitude"] == pytest.approx(YABA[0]) and road["stale"] is False and road["last_seen_seconds"] < 120
    assert road["job"]["status"] == "en_route" and road["job"]["order_ref"] == order["external_ref"]
    assert 20 <= road["job"]["eta_minutes"] <= 60  # about 10 km of city driving
    assert by_name["Gone Quiet"]["stale"] is True and by_name["Gone Quiet"]["job"] is None
    assert by_name["Never Reported"]["latitude"] is None and by_name["Never Reported"]["stale"] is True
    assert [w["order_ref"] for w in view["waiting"]] == [waiting["external_ref"]]  # unassigned drop-offs show as waiting pins
    assert stale and silent


def test_only_operations_staff_may_watch_drivers(company, as_user) -> None:
    t = company["tenant"]
    as_user(company["shop_user"])
    assert client.get(f"/api/v1/tenants/{t}/tracking/drivers").status_code == 403


def test_a_customer_sees_the_rider_only_while_their_parcel_is_on_the_way(company) -> None:
    t = company["tenant"]
    rider = new_driver(company, YABA, name="Ada Rider")
    order = new_order(company)
    token, job = order["tracking_token"], order["delivery_job_id"]

    assert customer_view(token)["rider"] is None  # nobody assigned yet
    client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/assignments", json={"driver_id": rider})
    assert customer_view(token)["rider"] is None  # assigned, not yet on the way
    move(company, job, "accepted")
    assert customer_view(token)["rider"] is None

    move(company, job, "en_route")
    seen = customer_view(token)
    assert seen["driver_first_name"] == "Ada"
    assert seen["rider"]["latitude"] == pytest.approx(YABA[0]) and seen["rider"]["eta_minutes"] >= 1
    assert seen["rider"]["dropoff"] == {"latitude": pytest.approx(IKEJA[0]), "longitude": pytest.approx(IKEJA[1])}
    flat = str(seen)
    assert "+234" not in flat and rider not in flat  # no phone numbers or internal driver ids

    with Session(engine) as session:  # the rider's phone went quiet 20 minutes ago: do not pretend it is live
        driver = session.get(Driver, UUID(rider))
        driver.last_location_at = utc_now() - timedelta(minutes=20)
        session.add(driver)
        session.commit()
    assert customer_view(token)["rider"] is None

    with Session(engine) as session:
        driver = session.get(Driver, UUID(rider))
        driver.last_location_at = utc_now()
        session.add(driver)
        session.commit()
    move(company, job, "arrived", "delivered")
    assert customer_view(token)["rider"] is None  # after delivery the customer sees nothing more
