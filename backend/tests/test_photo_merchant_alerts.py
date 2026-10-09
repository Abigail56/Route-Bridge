import base64
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.db.session import create_db_and_tables, engine
from routebridge.main import app
from routebridge.models.core import Tenant
from routebridge.models.plans import NotificationDelivery
from routebridge.models.workflows import Notification

client = TestClient(app)
create_db_and_tables()


def data_url(raw: bytes, kind: str = "jpeg") -> str:
    return f"data:image/{kind};base64," + base64.b64encode(raw).decode()


JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


@pytest.fixture
def company():
    with Session(engine) as session:
        tenant = Tenant(name="Photo Logistics")
        session.add(tenant)
        session.commit()
        return str(tenant.id)


def new_driver(t: str) -> str:
    return client.post(f"/api/v1/tenants/{t}/drivers", json={"name": "Ada Rider", "phone": f"+23480{uuid4().int % 10**8:08d}"}).json()["id"]


def notes_for(phone: str) -> list[tuple[Notification, str]]:
    with Session(engine) as session:
        rows = session.exec(select(Notification).where(Notification.recipient == phone)).all()
        return [(n, session.exec(select(NotificationDelivery).where(NotificationDelivery.notification_id == n.id)).one().body) for n in rows]


def test_a_rider_picture_is_saved_shown_and_removed(company) -> None:
    d = new_driver(company)
    url = f"/api/v1/tenants/{company}/drivers/{d}/photo"
    assert client.put(url, json={"data_url": data_url(JPEG)}).status_code == 200
    listed = {row["id"]: row for row in client.get(f"/api/v1/tenants/{company}/drivers").json()}
    assert listed[d]["photo"].startswith("data:image/jpeg;base64,")
    assert client.put(url, json={"data_url": data_url(PNG, "png")}).status_code == 200
    assert client.delete(url).json() == {"photo": None}


def test_bad_pictures_are_refused(company) -> None:
    d = new_driver(company)
    url = f"/api/v1/tenants/{company}/drivers/{d}/photo"
    assert client.put(url, json={"data_url": data_url(b"<script>alert(1)</script>" * 4)}).status_code == 422  # not really a jpeg
    assert client.put(url, json={"data_url": data_url(JPEG + b"\x00" * 50_000)}).status_code == 413  # too big
    assert client.put(url, json={"data_url": "data:text/html;base64," + base64.b64encode(b"<b>x</b>" * 10).decode()}).status_code == 422
    assert client.put(url, json={"data_url": "data:image/jpeg;base64,@@@@" + "A" * 40}).status_code == 422
    assert client.put(url, json={"data_url": data_url(b"RIFF" + b"\x00" * 100, "webp")}).status_code == 422  # riff but not webp
    other = str(uuid4())
    assert client.put(f"/api/v1/tenants/{company}/drivers/{other}/photo", json={"data_url": data_url(JPEG)}).status_code == 404


def test_a_rider_of_another_company_cannot_be_changed(company) -> None:
    with Session(engine) as session:
        other = Tenant(name="Elsewhere Logistics")
        session.add(other)
        session.commit()
        other_id = str(other.id)
    foreign = new_driver(other_id)
    assert client.put(f"/api/v1/tenants/{company}/drivers/{foreign}/photo", json={"data_url": data_url(JPEG)}).status_code == 404


def test_a_new_shop_with_a_number_gets_a_welcome_and_then_a_text_per_order(company) -> None:
    phone = f"+23481{uuid4().int % 10**8:08d}"
    shop = client.post(f"/api/v1/admin/tenants/{company}/merchants", json={"clerk_user_id": f"user_shop_{__import__('uuid').uuid4().hex[:10]}", "name": "Mama Put Foods", "contact_phone": phone}).json()
    assert shop["contact_phone"] == phone and shop["notify_orders"] is True
    welcome = notes_for(phone)
    assert len(welcome) == 1 and welcome[0][0].template == "merchant_welcome" and "Mama Put Foods" in welcome[0][1]
    res = client.post(f"/api/v1/tenants/{company}/orders", json={"merchant_id": shop["id"], "customer_name": "Chidi", "customer_phone": "+2348011112222", "external_ref": "MP-77", "address_text": "4 Bode Thomas Street"})
    assert res.status_code == 201
    texts = [body for note, body in notes_for(phone) if note.template == "merchant_order_created"]
    assert len(texts) == 1 and "MP-77" in texts[0] and "Chidi" in texts[0] and "Bode Thomas" in texts[0]


def test_no_number_or_switched_off_means_no_text(company) -> None:
    silent = client.post(f"/api/v1/admin/tenants/{company}/merchants", json={"clerk_user_id": f"user_shop_{__import__('uuid').uuid4().hex[:10]}", "name": "No Phone Shop"}).json()
    client.post(f"/api/v1/tenants/{company}/orders", json={"merchant_id": silent["id"], "customer_name": "C", "customer_phone": "+2348011112223", "external_ref": "NP-1", "address_text": "x"})
    phone = f"+23481{uuid4().int % 10**8:08d}"
    muted = client.post(f"/api/v1/admin/tenants/{company}/merchants", json={"clerk_user_id": f"user_shop_{__import__('uuid').uuid4().hex[:10]}", "name": "Muted Shop", "contact_phone": phone}).json()
    assert client.patch(f"/api/v1/admin/tenants/{company}/merchants/{muted['id']}", json={"notify_orders": False}).json()["notify_orders"] is False
    client.post(f"/api/v1/tenants/{company}/orders", json={"merchant_id": muted["id"], "customer_name": "C", "customer_phone": "+2348011112224", "external_ref": "MU-1", "address_text": "x"})
    assert [n.template for n, _ in notes_for(phone)] == ["merchant_welcome"]  # welcome only, nothing for the order


def test_editing_a_shops_contact_details_and_bad_numbers(company) -> None:
    shop = client.post(f"/api/v1/admin/tenants/{company}/merchants", json={"clerk_user_id": f"user_shop_{__import__('uuid').uuid4().hex[:10]}", "name": "Edit Shop"}).json()
    url = f"/api/v1/admin/tenants/{company}/merchants/{shop['id']}"
    assert client.patch(url, json={"contact_phone": "+2348099998888"}).json()["contact_phone"] == "+2348099998888"
    assert client.patch(url, json={"contact_phone": "call me"}).status_code == 422
    assert client.post(f"/api/v1/admin/tenants/{company}/merchants", json={"clerk_user_id": f"user_shop_{__import__('uuid').uuid4().hex[:10]}", "name": "Bad Phone", "contact_phone": "<script>"}).status_code == 422
    assert client.patch(f"/api/v1/admin/tenants/{company}/merchants/{uuid4()}", json={"notify_orders": False}).status_code == 404
