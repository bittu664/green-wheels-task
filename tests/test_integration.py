import os
from time import monotonic, sleep
from uuid import uuid4

import httpx
import pytest

BASE = os.getenv("LEASE_TEST_URL")


@pytest.mark.skipif(not BASE, reason="Set LEASE_TEST_URL for a running Compose stack")
def test_payment_replay_and_metrics():
    driver = f"test-{uuid4()}"
    fact = {"event_id": str(uuid4()), "driver_id": driver, "event_type": "payment_made"}
    with httpx.Client(base_url=BASE, timeout=3) as client:
        first = client.post("/leases/events", json=fact)
        retry = client.post("/leases/events", json=fact)
        assert first.status_code == retry.status_code == 202
        assert first.json() == retry.json()
        assert client.post("/leases/events", json={**fact, "event_type": "payment_missed"}
                           ).status_code == 409
        deadline = monotonic() + 30
        while monotonic() < deadline:
            lease = client.get(f"/leases/{driver}")
            if lease.status_code == 200:
                break
            sleep(.25)
        assert lease.status_code == 200
        assert lease.json()["payment_cycle"] == 1
        assert lease.json()["version"] == 1
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert (
            'lease_http_requests_total{method="POST",outcome="good",'
            'route="/leases/events",status_class="2xx"}'
        ) in metrics.text
        assert (
            'lease_http_duration_seconds_bucket{le="0.3",method="GET",'
            'outcome="good",route="/leases/{driver_id}"}'
        ) in metrics.text
