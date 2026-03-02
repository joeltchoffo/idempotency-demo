import uuid
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_same_key_replays_same_order():
    key = str(uuid.uuid4())
    payload = {
        "customer_id": "cust_123",
        "currency": "EUR",
        "amount_cents": 1999,
        "items": [{"sku": "sku_abc", "qty": 1, "unit_price_cents": 1999}],
    }

    r1 = client.post("/orders", json=payload, headers={"Idempotency-Key": key})
    assert r1.status_code == 201
    assert r1.headers["Idempotency-Replayed"] == "false"
    order_id_1 = r1.json()["order_id"]

    r2 = client.post("/orders", json=payload, headers={"Idempotency-Key": key})
    assert r2.status_code == 201
    assert r2.headers["Idempotency-Replayed"] == "true"
    assert r2.json()["order_id"] == order_id_1


def test_same_key_different_body_is_conflict():
    key = str(uuid.uuid4())

    payload1 = {"customer_id": "cust_123", "currency": "EUR", "amount_cents": 100}
    payload2 = {"customer_id": "cust_123", "currency": "EUR", "amount_cents": 200}

    r1 = client.post("/orders", json=payload1, headers={"Idempotency-Key": key})
    assert r1.status_code == 201

    r2 = client.post("/orders", json=payload2, headers={"Idempotency-Key": key})
    assert r2.status_code == 409


def test_missing_idempotency_key_is_400():
    payload = {"customer_id": "cust_123", "currency": "EUR", "amount_cents": 100}
    r = client.post("/orders", json=payload)
    assert r.status_code == 400