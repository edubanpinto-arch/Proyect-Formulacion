from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import server


class DevicesCollection:
    async def update_one(self, *_args, **_kwargs):
        return SimpleNamespace(matched_count=0)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "db", SimpleNamespace(devices=DevicesCollection()))
    audit_calls = []

    async def audit(*_args, **_kwargs):
        audit_calls.append(True)

    monkeypatch.setattr(server, "audit", audit)
    for route in server.app.routes:
        if getattr(route, "path", None) in {
            "/api/devices/reject",
            "/api/devices/{device_id}/readings",
        }:
            for dependency in route.dependant.dependencies:
                monkeypatch.setitem(
                    server.app.dependency_overrides,
                    dependency.call,
                    lambda: {"email": "admin@example.com", "role": "admin"},
                )

    with TestClient(server.app) as test_client:
        yield test_client, audit_calls


def test_reject_unknown_device_returns_404_without_audit(client):
    test_client, audit_calls = client

    response = test_client.post("/api/devices/reject", json={"device_id": "MISSING"})

    assert response.status_code == 404
    assert audit_calls == []


@pytest.mark.parametrize("limit", [0, -1, 5001])
def test_readings_rejects_out_of_range_limit(client, limit):
    test_client, _audit_calls = client

    response = test_client.get("/api/devices/device/readings", params={"limit": limit})

    assert response.status_code == 422
