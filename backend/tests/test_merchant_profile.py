"""Shops are added by their own sign-in id, register their own details, and the people who need them can see them (and only them)."""
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from routebridge.auth.dependencies import get_optional_user
from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.integrations.clerk import ClerkUser
from routebridge.main import app
from routebridge.models.core import Tenant

client = TestClient(app)
create_db_and_tables()

PROFILE = {"contact_phone": "+2348012345678", "contact_person": "Ada Obi", "address_line": "12 Allen Avenue", "landmark": "Opposite the bank", "city": "Ikeja", "state": "Lagos", "bank_name": "GTBank", "account_number": "0123456789", "account_name": "Ada Foods Ltd"}


def _id() -> str:
    return f"user_{uuid4().hex[:12]}"


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
        tenant, other = Tenant(name="Profile Test Logistics"), Tenant(name="Somebody Else Logistics")
        session.add_all([tenant, other])
        session.commit()
        tid, oid = str(tenant.id), str(other.id)
    people = {"owner": _id(), "dispatcher": _id(), "finance": _id(), "boss": _id(), "stranger": _id()}
    as_user(people["boss"], listed_admin=True)
    assert client.post(f"/api/v1/platform/tenants/{tid}/owner", json={"clerk_user_id": people["owner"]}).status_code == 200
    assert client.post(f"/api/v1/platform/tenants/{oid}/owner", json={"clerk_user_id": people["stranger"]}).status_code == 200
    for who in ("dispatcher", "finance"):
        assert client.post(f"/api/v1/platform/tenants/{tid}/members", json={"clerk_user_id": people[who], "role": who}).status_code == 201
    as_user(people["owner"])
    return {"tenant": tid, "other": oid, "people": people}


def _add_shop(t: str, name: str, user: str, **extra):
    return client.post(f"/api/v1/admin/tenants/{t}/merchants", json={"name": name, "clerk_user_id": user, **extra})


def test_a_shop_cannot_be_added_without_its_user_id_and_the_id_cannot_be_reused(company, as_user) -> None:
    t, people = company["tenant"], company["people"]
    assert client.post(f"/api/v1/admin/tenants/{t}/merchants", json={"name": "No Id Shop"}).status_code == 422
    assert client.post(f"/api/v1/admin/tenants/{t}/merchants", json={"name": "Blank Id", "clerk_user_id": "  "}).status_code == 422
    shop_user = _id()
    created = _add_shop(t, "Ada Foods", shop_user)
    assert created.status_code == 201, created.text
    # the same id cannot front a second shop, and a colleague's id cannot be turned into a shop
    assert _add_shop(t, "Copy Shop", shop_user).status_code == 409
    assert _add_shop(t, "Staff Shop", people["dispatcher"]).status_code == 409
    members = {m["clerk_user_id"]: m for m in client.get(f"/api/v1/tenants/{t}/members").json()}
    assert members[shop_user]["role"] == "merchant_user" and members[shop_user]["merchant_name"] == "Ada Foods"
    # only the owner may add shops
    as_user(people["dispatcher"])
    assert _add_shop(t, "Sneaky", _id()).status_code == 403


def test_the_shop_registers_itself_and_cannot_order_until_it_has(company, as_user) -> None:
    t = company["tenant"]
    shop_user = _id()
    assert _add_shop(t, "Ada Foods", shop_user).status_code == 201
    as_user(shop_user)
    me = client.get(f"/api/v1/tenants/{t}/portal/me").json()
    assert me["merchant_name"] == "Ada Foods" and me["profile_complete"] is False
    order = {"customer_name": "Bola", "customer_phone": "+2348099990000", "address_text": "9 Test Street"}
    refused = client.post(f"/api/v1/tenants/{t}/portal/orders", json=order)
    assert refused.status_code == 422 and "registering" in refused.json()["detail"]
    for bad, why in (({"account_number": "12345"}, "short"), ({"account_number": "01234abcde"}, "letters"), ({"contact_phone": "call me"}, "phone"), ({"city": ""}, "city"), ({"merchant_id": str(uuid4())}, "cannot name a shop")):
        assert client.put(f"/api/v1/tenants/{t}/portal/profile", json={**PROFILE, **bad}).status_code == 422, why
    missing = {k: v for k, v in PROFILE.items() if k != "bank_name"}
    assert client.put(f"/api/v1/tenants/{t}/portal/profile", json=missing).status_code == 422
    saved = client.put(f"/api/v1/tenants/{t}/portal/profile", json={**PROFILE, "account_number": "0123 456 789"})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["complete"] is True and body["account_number"] == "0123456789" and body["address_line"] == "12 Allen Avenue"
    assert client.get(f"/api/v1/tenants/{t}/portal/me").json()["profile_complete"] is True
    assert client.post(f"/api/v1/tenants/{t}/portal/orders", json=order).status_code == 201
    # it can change its details later
    changed = client.put(f"/api/v1/tenants/{t}/portal/profile", json={**PROFILE, "city": "Yaba"})
    assert changed.status_code == 200 and changed.json()["city"] == "Yaba"


def test_the_owner_sees_every_shops_details_but_only_money_roles_see_bank_accounts(company, as_user) -> None:
    t, people = company["tenant"], company["people"]
    shop_user, quiet_user = _id(), _id()
    assert _add_shop(t, "Ada Foods", shop_user).status_code == 201
    assert _add_shop(t, "Not Registered Yet", quiet_user).status_code == 201
    as_user(shop_user)
    assert client.put(f"/api/v1/tenants/{t}/portal/profile", json=PROFILE).status_code == 200

    def listed(who: str) -> dict:
        as_user(people[who])
        res = client.get(f"/api/v1/tenants/{t}/merchant-profiles")
        assert res.status_code == 200, (who, res.text)
        return {row["merchant_name"]: row for row in res.json()}

    owner_view = listed("owner")
    ada = owner_view["Ada Foods"]
    assert ada["complete"] is True and ada["address_line"] == "12 Allen Avenue" and ada["contact_phone"] == "+2348012345678"
    assert ada["bank_name"] == "GTBank" and ada["account_number"] == "0123456789" and ada["account_name"] == "Ada Foods Ltd"
    assert owner_view["Not Registered Yet"]["complete"] is False and owner_view["Not Registered Yet"]["account_number"] is None
    finance_view = listed("finance")["Ada Foods"]
    assert finance_view["account_number"] == "0123456789"
    desk_view = listed("dispatcher")["Ada Foods"]
    assert desk_view["address_line"] == "12 Allen Avenue" and desk_view["bank_visible"] is False
    assert desk_view["account_number"] is None and desk_view["bank_name"] is None and desk_view["account_name"] is None
    # a shop cannot read the staff list, and another company's owner sees none of these shops
    as_user(shop_user)
    assert client.get(f"/api/v1/tenants/{t}/merchant-profiles").status_code == 403
    as_user(people["stranger"])
    assert client.get(f"/api/v1/tenants/{t}/merchant-profiles").status_code == 403
    assert client.get(f"/api/v1/tenants/{company['other']}/merchant-profiles").json() == []


def test_one_shop_cannot_read_or_change_another_shops_details(company, as_user) -> None:
    t = company["tenant"]
    first, second = _id(), _id()
    assert _add_shop(t, "First Shop", first).status_code == 201
    assert _add_shop(t, "Second Shop", second).status_code == 201
    as_user(first)
    assert client.put(f"/api/v1/tenants/{t}/portal/profile", json=PROFILE).status_code == 200
    as_user(second)
    mine = client.get(f"/api/v1/tenants/{t}/portal/profile").json()
    assert mine["merchant_name"] == "Second Shop" and mine["address_line"] is None and mine["account_number"] is None
    assert client.put(f"/api/v1/tenants/{t}/portal/profile", json={**PROFILE, "address_line": "2 Other Road", "account_number": "9999999999"}).status_code == 200
    as_user(first)
    assert client.get(f"/api/v1/tenants/{t}/portal/profile").json()["address_line"] == "12 Allen Avenue"


def test_the_rider_sees_the_shop_to_collect_from_but_never_its_bank_account(company, as_user, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "driver_token_secret", "d" * 32)
    t = company["tenant"]
    shop_user = _id()
    shop = _add_shop(t, "Ada Foods", shop_user).json()
    as_user(shop_user)
    assert client.put(f"/api/v1/tenants/{t}/portal/profile", json=PROFILE).status_code == 200
    as_user(company["people"]["owner"])
    order = client.post(f"/api/v1/tenants/{t}/orders", json={"merchant_id": shop["id"], "customer_name": "Bola", "customer_phone": "+2348055550000", "external_ref": f"R-{uuid4().hex[:6]}", "cod_amount": "1000", "total_amount": "1000", "address_text": "Surulere"}).json()
    driver = client.post(f"/api/v1/tenants/{t}/drivers", json={"name": "Chisom Obi", "phone": "08066660000"}).json()
    assert client.post(f"/api/v1/tenants/{t}/delivery-jobs/{order['delivery_job_id']}/assignments", json={"driver_id": driver["id"]}).status_code == 201
    token = client.post(f"/api/v1/tenants/{t}/drivers/{driver['id']}/token").json()["access_token"]
    jobs = client.get(f"/api/v1/driver/tenants/{t}/jobs", headers={"Authorization": f"Bearer {token}"})
    assert jobs.status_code == 200 and len(jobs.json()) == 1
    card = jobs.json()[0]["merchant"]
    assert card["name"] == "Ada Foods" and card["phone"] == "+2348012345678" and card["contact_person"] == "Ada Obi"
    assert card["address"] == "12 Allen Avenue, Opposite the bank, Ikeja, Lagos"
    assert not any(secret in json.dumps(jobs.json()) for secret in ("0123456789", "GTBank", "Ada Foods Ltd"))


def test_removing_a_shop_switches_off_its_login_keeps_its_history_and_frees_the_user_id(company, as_user) -> None:
    t, people = company["tenant"], company["people"]
    busy_user, idle_user = _id(), _id()
    busy = _add_shop(t, "Busy Shop", busy_user).json()
    idle = _add_shop(t, "Idle Shop", idle_user).json()
    as_user(busy_user)
    assert client.put(f"/api/v1/tenants/{t}/portal/profile", json=PROFILE).status_code == 200
    as_user(people["owner"])
    order = client.post(f"/api/v1/tenants/{t}/orders", json={"merchant_id": busy["id"], "customer_name": "Bola", "customer_phone": "+2348055550000", "external_ref": f"X-{uuid4().hex[:6]}", "cod_amount": "0", "total_amount": "0", "address_text": "Surulere"})
    assert order.status_code == 201
    # nobody but the owner may remove a shop; one with a delivery still on the way cannot be removed
    as_user(people["dispatcher"])
    assert client.delete(f"/api/v1/admin/tenants/{t}/merchants/{idle['id']}").status_code == 403
    as_user(people["owner"])
    refused = client.delete(f"/api/v1/admin/tenants/{t}/merchants/{busy['id']}")
    assert refused.status_code == 409 and "on the way" in refused.json()["detail"]
    assert client.delete(f"/api/v1/admin/tenants/{t}/merchants/{uuid4()}").status_code == 404
    # an idle shop goes: gone from every list, its login locked out, orders cannot be created for it
    done = client.delete(f"/api/v1/admin/tenants/{t}/merchants/{idle['id']}")
    assert done.status_code == 200 and done.json() == {"removed": True, "logins_switched_off": 1}
    assert idle["id"] not in [m["id"] for m in client.get(f"/api/v1/admin/tenants/{t}/merchants").json()]
    assert idle["id"] not in [m["id"] for m in client.get(f"/api/v1/tenants/{t}/merchants").json()]
    assert "Idle Shop" not in [row["merchant_name"] for row in client.get(f"/api/v1/tenants/{t}/merchant-profiles").json()]
    assert client.delete(f"/api/v1/admin/tenants/{t}/merchants/{idle['id']}").status_code == 404  # already gone
    blocked = client.post(f"/api/v1/tenants/{t}/orders", json={"merchant_id": idle["id"], "customer_name": "Bola", "customer_phone": "+2348055550000", "external_ref": f"Y-{uuid4().hex[:6]}", "address_text": "Yaba"})
    assert blocked.status_code == 409
    as_user(idle_user)
    assert client.get(f"/api/v1/tenants/{t}/portal/me").status_code == 403
    # the same user id can front a new shop
    as_user(people["owner"])
    again = _add_shop(t, "Fresh Start Shop", idle_user)
    assert again.status_code == 201, again.text
    as_user(idle_user)
    assert client.get(f"/api/v1/tenants/{t}/portal/me").json()["merchant_name"] == "Fresh Start Shop"


def test_a_removed_shop_can_be_listed_and_restored_with_its_login(company, as_user) -> None:
    t, people = company["tenant"], company["people"]
    shop_user = _id()
    shop = _add_shop(t, "Bring Me Back Shop", shop_user).json()
    as_user(shop_user)
    assert client.put(f"/api/v1/tenants/{t}/portal/profile", json=PROFILE).status_code == 200
    as_user(people["owner"])
    assert client.get(f"/api/v1/admin/tenants/{t}/removed-merchants").json() == []
    assert client.post(f"/api/v1/admin/tenants/{t}/merchants/{shop['id']}/restore").status_code == 404  # still active: nothing to restore
    assert client.delete(f"/api/v1/admin/tenants/{t}/merchants/{shop['id']}").status_code == 200
    removed = client.get(f"/api/v1/admin/tenants/{t}/removed-merchants").json()
    assert [m["id"] for m in removed] == [shop["id"]]
    # only the owner can restore; the shop's own login stays locked until then
    as_user(people["dispatcher"])
    assert client.post(f"/api/v1/admin/tenants/{t}/merchants/{shop['id']}/restore").status_code == 403
    assert client.get(f"/api/v1/admin/tenants/{t}/removed-merchants").status_code == 403
    as_user(shop_user)
    assert client.get(f"/api/v1/tenants/{t}/portal/me").status_code == 403
    as_user(people["owner"])
    done = client.post(f"/api/v1/admin/tenants/{t}/merchants/{shop['id']}/restore")
    assert done.status_code == 200 and done.json() == {"restored": True, "logins_switched_on": 1}
    assert client.get(f"/api/v1/admin/tenants/{t}/removed-merchants").json() == []
    assert shop["id"] in [m["id"] for m in client.get(f"/api/v1/admin/tenants/{t}/merchants").json()]
    # the shop signs in again and finds its registration and history intact
    as_user(shop_user)
    me = client.get(f"/api/v1/tenants/{t}/portal/me").json()
    assert me["merchant_name"] == "Bring Me Back Shop" and me["profile_complete"] is True
    # another company's owner cannot restore this shop
    as_user(people["owner"])
    assert client.delete(f"/api/v1/admin/tenants/{t}/merchants/{shop['id']}").status_code == 200
    as_user(people["stranger"])
    assert client.post(f"/api/v1/admin/tenants/{t}/merchants/{shop['id']}/restore").status_code == 403
