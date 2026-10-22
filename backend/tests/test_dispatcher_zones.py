"""Dispatchers work in zones: they name them when they register, the Admin can change them, and jobs only go to riders who cover the zone."""
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from helpers import make_zone, post_order
from sqlmodel import Session

from routebridge.auth.dependencies import get_optional_user
from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.integrations.sessions import AuthUser
from routebridge.main import app
from routebridge.models.core import Tenant
from routebridge.models.operations import Driver
from routebridge.models.orders import Merchant

client = TestClient(app)
create_db_and_tables()

PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
IKEJA = (6.6018, 3.3515)
YABA = (6.5095, 3.3711)


def _id() -> str:
    return f"user_{uuid4().hex[:12]}"


@pytest.fixture
def as_user():
    settings = get_settings()
    old = (settings.require_auth, list(settings.platform_admin_subjects))
    settings.require_auth = True

    def sign_in(subject: str, listed_admin: bool = False):
        app.dependency_overrides[get_optional_user] = lambda: AuthUser(subject, {"email": f"{subject}@example.test"})
        settings.platform_admin_subjects[:] = [subject] if listed_admin else []

    yield sign_in
    app.dependency_overrides.pop(get_optional_user, None)
    settings.require_auth = old[0]
    settings.platform_admin_subjects[:] = old[1]


@pytest.fixture
def company(as_user):
    with Session(engine) as session:
        tenant = Tenant(name="Zone Test Logistics")
        session.add(tenant)
        session.flush()
        merchant = Merchant(tenant_id=tenant.id, name="Shop")
        session.add(merchant)
        session.commit()
        t, m = str(tenant.id), str(merchant.id)
    owner, shop_user, boss = _id(), _id(), _id()
    as_user(boss, listed_admin=True)
    assert client.post(f"/api/v1/platform/tenants/{t}/owner", json={"clerk_user_id": owner}).status_code == 200
    assert client.post(f"/api/v1/platform/tenants/{t}/members", json={"clerk_user_id": shop_user, "role": "merchant_user", "merchant_id": m}).status_code == 201
    as_user(owner)
    return {"tenant": t, "merchant": m, "owner": owner, "shop_user": shop_user, "lagos": make_zone(t, "Lagos"), "abuja": make_zone(t, "Abuja")}


def rider(company, name, place=None) -> str:
    with Session(engine) as session:
        row = Driver(tenant_id=UUID(company["tenant"]), name=name, phone=f"+23480{uuid4().int % 10**8:08d}", latitude=place[0] if place else None, longitude=place[1] if place else None)
        session.add(row)
        session.commit()
        return str(row.id)


def set_zones(company, driver_id, *zones):
    return client.put(f"/api/v1/tenants/{company['tenant']}/drivers/{driver_id}/zones", json={"zone_ids": list(zones)})


def job_in(company, zone, place=None) -> str:
    body = {"merchant_id": company["merchant"], "customer_name": "Cust", "customer_phone": "+2348011111111", "external_ref": f"Z-{uuid4().hex[:8]}", "address_text": "somewhere", "service_zone_id": zone}
    if place:
        body["latitude"], body["longitude"] = place
    res = post_order(client, f"/api/v1/tenants/{company['tenant']}/orders", json=body)
    assert res.status_code == 201, res.text
    return res.json()["delivery_job_id"]


def test_the_areas_a_rider_registers_become_their_zones_when_the_admin_adds_them(company, as_user) -> None:
    t, person = company["tenant"], _id()
    as_user(person)
    saved = client.put("/api/v1/auth/me/rider-registration", json={"full_name": "Musa Bello", "phone": "+2348011112222", "photo": PNG, "zones": [" lagos ", "LAGOS", "Kano"]})
    assert saved.status_code == 200 and saved.json()["zones"] == ["lagos", "Kano"] and saved.json()["complete"] is True
    as_user(company["owner"])
    added = client.post(f"/api/v1/tenants/{t}/members", json={"clerk_user_id": person, "role": "driver", "fleet_type": "staff"})
    assert added.status_code == 201, added.text
    row = next(d for d in client.get(f"/api/v1/tenants/{t}/drivers").json() if d["id"] == added.json()["driver_id"])
    # Lagos matched the company's zone (any case); Kano is not a zone here, so it is only shown as what they asked for
    assert row["zone_ids"] == [company["lagos"]] and row["requested_zones"] == ["lagos", "Kano"]


def test_a_rider_who_registered_without_zones_cannot_be_added_yet(company, as_user) -> None:
    from routebridge.models.access import User

    t, person = company["tenant"], _id()
    with Session(engine) as session:  # registered before zones were asked for
        session.add(User(clerk_user_id=person, full_name="Old Rider", phone="+2348011113333", photo=PNG))
        session.commit()
    added = client.post(f"/api/v1/tenants/{t}/members", json={"clerk_user_id": person, "role": "driver", "fleet_type": "staff"})
    assert added.status_code == 422 and "zones" in added.json()["detail"]


def test_manual_assignment_outside_the_riders_zones_is_refused(company) -> None:
    t = company["tenant"]
    abuja_rider = rider(company, "Abuja Rider")
    assert set_zones(company, abuja_rider, company["abuja"]).status_code == 200
    job = job_in(company, company["lagos"])
    refused = client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/assignments", json={"driver_id": abuja_rider})
    assert refused.status_code == 409 and "Lagos" in refused.json()["detail"] and "Abuja" in refused.json()["detail"]
    # once Lagos is added to their zones, the same assignment works
    assert set_zones(company, abuja_rider, company["abuja"], company["lagos"]).status_code == 200
    assert client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/assignments", json={"driver_id": abuja_rider}).status_code == 201


def test_automatic_assignment_only_picks_riders_in_the_jobs_zone(company) -> None:
    t = company["tenant"]
    near_wrong_zone = rider(company, "Abuja Rider Nearby", YABA)
    set_zones(company, near_wrong_zone, company["abuja"])
    job = job_in(company, company["lagos"], place=IKEJA)
    res = client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/auto-assign").json()
    assert not res["assigned"] and res["reason"] == "no_driver_in_zone"
    lagos_rider = rider(company, "Lagos Rider")  # no position shared yet: chosen as the next free rider in the zone
    set_zones(company, lagos_rider, company["lagos"])
    res = client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/auto-assign").json()
    assert res["assigned"] and res["driver_id"] == lagos_rider


def test_the_nearest_rider_in_the_zone_wins_over_a_nearer_one_outside_it(company) -> None:
    t = company["tenant"]
    set_zones(company, rider(company, "Abuja Rider Closest", IKEJA), company["abuja"])
    lagos_rider = rider(company, "Lagos Rider Further", YABA)
    set_zones(company, lagos_rider, company["lagos"])
    res = client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job_in(company, company['lagos'], place=IKEJA)}/auto-assign").json()
    assert res["assigned"] and res["driver_id"] == lagos_rider and res["method"] == "nearest"


def test_a_rider_with_no_zones_set_covers_every_zone(company) -> None:
    t = company["tenant"]
    anywhere = rider(company, "Anywhere Rider")
    assert client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job_in(company, company['abuja'])}/assignments", json={"driver_id": anywhere}).status_code == 201


def test_only_the_admin_sets_zones_and_only_this_companys_zones(company, as_user) -> None:
    t = company["tenant"]
    someone = rider(company, "Some Rider")
    other_company = Tenant(name="Elsewhere")
    with Session(engine) as session:
        session.add(other_company)
        session.commit()
        foreign = make_zone(str(other_company.id), "Foreign Zone")
    assert set_zones(company, someone, foreign).status_code == 404
    assert set_zones(company, someone, str(uuid4())).status_code == 404
    as_user(company["shop_user"])
    assert set_zones(company, someone, company["lagos"]).status_code == 403
    as_user(company["owner"])
    assert set_zones(company, someone).json()["zone_ids"] == []  # empty = every zone again


def test_rate_card_cash_on_delivery_fee_is_saved(company) -> None:
    t = company["tenant"]
    card = client.post(f"/api/v1/tenants/{t}/rate-cards", json={"service_zone_id": company["lagos"], "name": "Lagos standard", "base_amount": "1500", "cod_fee": "200"})
    assert card.status_code == 201, card.text
    assert card.json()["cod_fee"] == "200.00" and card.json()["base_amount"] == "1500.00"
