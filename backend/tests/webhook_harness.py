"""A small, deterministic replay harness for webhooks.

A test describes a set of `Delivery` objects (a signed body and its headers) and chooses HOW they arrive:
in order, duplicated, shuffled with a seed (the same seed always gives the same order), or all at once from many threads released
together. Every answer is kept in `Replayer.log`, so a failing run prints exactly what was sent and what came back.
"""
import base64
import hashlib
import hmac
import json
import random
import threading
import time
from dataclasses import dataclass, field

from fastapi.testclient import TestClient


@dataclass(frozen=True)
class Delivery:
    label: str
    path: str
    body: bytes
    headers: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Answer:
    label: str
    status: int
    json: dict | None


def paystack(label: str, body: dict, secret: str, *, valid: bool = True) -> Delivery:
    raw = json.dumps(body).encode()
    key = secret if valid else secret + "-wrong"
    return Delivery(label, "/api/v1/webhooks/paystack", raw, {"x-paystack-signature": hmac.new(key.encode(), raw, hashlib.sha512).hexdigest(), "content-type": "application/json"})


def svix(label: str, body: dict, secret: str, msg_id: str, *, timestamp: int | None = None) -> Delivery:
    raw = json.dumps(body).encode()
    ts = str(timestamp if timestamp is not None else int(time.time()))
    key = base64.b64decode(secret.split("_", 1)[1])
    sig = base64.b64encode(hmac.new(key, f"{msg_id}.{ts}.".encode() + raw, hashlib.sha256).digest()).decode()
    return Delivery(label, "/api/v1/webhooks/clerk", raw, {"svix-id": msg_id, "svix-timestamp": ts, "svix-signature": f"v1,{sig}", "content-type": "application/json"})


class Replayer:
    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.log: list[Answer] = []

    def send(self, delivery: Delivery) -> Answer:
        res = self.client.post(delivery.path, content=delivery.body, headers=delivery.headers)
        try:
            payload = res.json()
        except ValueError:
            payload = None
        answer = Answer(delivery.label, res.status_code, payload if isinstance(payload, dict) else None)
        self.log.append(answer)
        return answer

    def in_order(self, deliveries: list[Delivery]) -> list[Answer]:
        return [self.send(d) for d in deliveries]

    def duplicated(self, deliveries: list[Delivery], times: int) -> list[Answer]:
        return self.in_order([d for d in deliveries for _ in range(times)])

    def shuffled(self, deliveries: list[Delivery], seed: int) -> list[Answer]:
        order = list(deliveries)
        random.Random(seed).shuffle(order)
        return self.in_order(order)

    def at_once(self, deliveries: list[Delivery]) -> list[Answer]:
        """Every delivery on its own thread, released together by a barrier (a real race, not a loop)."""
        barrier = threading.Barrier(len(deliveries))
        answers: list[Answer | None] = [None] * len(deliveries)

        def run(index: int, delivery: Delivery) -> None:
            barrier.wait(timeout=30)
            answers[index] = self.send(delivery)

        threads = [threading.Thread(target=run, args=(i, d)) for i, d in enumerate(deliveries)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        return [a for a in answers if a is not None]

    def statuses(self, label: str | None = None) -> list[int]:
        return [a.status for a in self.log if label is None or a.label == label]

    def dump(self) -> str:
        return "\n".join(f"{a.label}: {a.status} {a.json}" for a in self.log)
