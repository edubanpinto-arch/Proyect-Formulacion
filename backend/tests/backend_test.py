"""ColdChain Dashboard E2E backend tests."""
import os
import time
import uuid
import pytest
import pyotp
import requests
from pymongo import MongoClient
import bcrypt

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://temp-guard-dash.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "edubanpinto@gmail.com"
ADMIN_PASS = "1234567890"
NEW_ADMIN_PASS = "NewStr0ngPass!234"
TRANS_EMAIL = "transportador@coldchain.com"
TRANS_PASS = "transport123"
DEVICE_ID = f"ESP32_TEST_{uuid.uuid4().hex[:6].upper()}"
DEVICE_PASS = "PASS_SECRETA_XYZ"


@pytest.fixture(scope="module")
def mongo():
    mc = MongoClient("mongodb://localhost:27017")
    yield mc["coldchain_db"]
    mc.close()


def reset_admin(mongo):
    """Reset admin to initial state."""
    ph = bcrypt.hashpw(ADMIN_PASS.encode(), bcrypt.gensalt()).decode()
    mongo.users.update_one(
        {"email": ADMIN_EMAIL},
        {"$set": {"password_hash": ph, "must_change_password": True,
                  "totp_enabled": False, "totp_secret": None}}
    )


@pytest.fixture(scope="module")
def admin_access(mongo):
    """Walk full admin onboarding: login -> change_password -> enroll_2fa -> access_token."""
    reset_admin(mongo)

    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["step"] == "change_password"
    temp = d["temp_token"]

    r = requests.post(f"{API}/auth/change-password",
                      json={"temp_token": temp, "new_password": NEW_ADMIN_PASS})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["step"] == "enroll_2fa"
    assert "secret" in d and "qr_data_url" in d
    secret = d["secret"]
    temp2 = d["temp_token"]

    code = pyotp.TOTP(secret).now()
    r = requests.post(f"{API}/auth/2fa/enroll-verify",
                      json={"temp_token": temp2, "code": code})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["step"] == "ok"
    assert "access_token" in d
    return {"token": d["access_token"], "secret": secret}


def auth_h(token):
    return {"Authorization": f"Bearer {token}"}


# ---- Auth tests ----
class TestAuthFlow:
    def test_full_admin_onboarding(self, admin_access):
        assert admin_access["token"]

    def test_auth_me(self, admin_access):
        r = requests.get(f"{API}/auth/me", headers=auth_h(admin_access["token"]))
        assert r.status_code == 200
        u = r.json()
        assert u["email"] == ADMIN_EMAIL
        assert u["role"] == "admin"

    def test_subsequent_admin_login_verify_2fa(self, admin_access):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": NEW_ADMIN_PASS})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["step"] == "verify_2fa"
        temp = d["temp_token"]
        code = pyotp.TOTP(admin_access["secret"]).now()
        r = requests.post(f"{API}/auth/2fa/verify", json={"temp_token": temp, "code": code})
        assert r.status_code == 200, r.text
        assert r.json()["step"] == "ok"
        assert "access_token" in r.json()

    def test_transporter_login_ok(self):
        r = requests.post(f"{API}/auth/login", json={"email": TRANS_EMAIL, "password": TRANS_PASS})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["step"] == "ok"
        assert d["user"]["role"] == "transporter"

    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
        assert r.status_code == 401


# ---- Device ingest + approval ----
class TestDeviceIngestFlow:
    def test_ingest_new_device_pending(self):
        r = requests.post(f"{API}/temperatura",
                          json={"deviceId": DEVICE_ID, "devicePassword": DEVICE_PASS, "temperature": 4.5})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "pending"

    def test_ingest_pending_again(self):
        r = requests.post(f"{API}/temperatura",
                          json={"deviceId": DEVICE_ID, "devicePassword": DEVICE_PASS, "temperature": 5.0})
        assert r.status_code == 200
        assert r.json()["status"] == "pending"

    def test_ingest_wrong_password(self):
        r = requests.post(f"{API}/temperatura",
                          json={"deviceId": DEVICE_ID, "devicePassword": "WRONG", "temperature": 5})
        assert r.status_code == 401

    def test_pending_visible_to_admin(self, admin_access):
        r = requests.get(f"{API}/devices/pending", headers=auth_h(admin_access["token"]))
        assert r.status_code == 200
        assert any(d["device_id"] == DEVICE_ID for d in r.json())

    def test_approve_device(self, admin_access):
        r = requests.post(f"{API}/devices/approve",
                          headers=auth_h(admin_access["token"]),
                          json={"device_id": DEVICE_ID, "name": "Test Vaccine"})
        assert r.status_code == 200, r.text

    def test_ingest_after_approval_normal(self):
        r = requests.post(f"{API}/temperatura",
                          json={"deviceId": DEVICE_ID, "devicePassword": DEVICE_PASS, "temperature": 5.0})
        assert r.status_code == 200
        j = r.json()
        assert j["status"] == "active"
        assert j["alert"] is None

    def test_ingest_warning_high(self):
        r = requests.post(f"{API}/temperatura",
                          json={"deviceId": DEVICE_ID, "devicePassword": DEVICE_PASS, "temperature": 7.6})
        assert r.status_code == 200
        assert r.json()["alert"] == "warning"

    def test_ingest_critical_high(self):
        r = requests.post(f"{API}/temperatura",
                          json={"deviceId": DEVICE_ID, "devicePassword": DEVICE_PASS, "temperature": 9.0})
        assert r.status_code == 200
        assert r.json()["alert"] == "critical"

    def test_ingest_critical_low(self):
        r = requests.post(f"{API}/temperatura",
                          json={"deviceId": DEVICE_ID, "devicePassword": DEVICE_PASS, "temperature": 1.5})
        assert r.status_code == 200
        assert r.json()["alert"] == "critical"


# ---- Admin list/stats/alerts ----
class TestAdminEndpoints:
    def test_list_devices(self, admin_access):
        r = requests.get(f"{API}/devices", headers=auth_h(admin_access["token"]))
        assert r.status_code == 200
        devs = r.json()
        mine = [d for d in devs if d["device_id"] == DEVICE_ID]
        assert mine and mine[0]["live_status"] in ("active", "inactive")

    def test_device_readings(self, admin_access):
        r = requests.get(f"{API}/devices/{DEVICE_ID}/readings", headers=auth_h(admin_access["token"]))
        assert r.status_code == 200
        assert len(r.json()) >= 3  # we sent several after approval

    def test_device_alerts(self, admin_access):
        r = requests.get(f"{API}/devices/{DEVICE_ID}/alerts", headers=auth_h(admin_access["token"]))
        assert r.status_code == 200
        assert len(r.json()) >= 3  # warning + 2 critical

    def test_list_alerts(self, admin_access):
        r = requests.get(f"{API}/alerts", headers=auth_h(admin_access["token"]))
        assert r.status_code == 200

    def test_ack_alert(self, admin_access):
        r = requests.get(f"{API}/alerts?active_only=true", headers=auth_h(admin_access["token"]))
        alerts = [a for a in r.json() if a["device_id"] == DEVICE_ID]
        assert alerts
        aid = alerts[0]["id"]
        r = requests.post(f"{API}/alerts/{aid}/ack", headers=auth_h(admin_access["token"]))
        assert r.status_code == 200

    def test_stats_summary(self, admin_access):
        r = requests.get(f"{API}/stats/summary", headers=auth_h(admin_access["token"]))
        assert r.status_code == 200
        s = r.json()
        for k in ("active", "inactive", "pending", "critical_alerts", "warning_alerts", "total_devices"):
            assert k in s


# ---- Transporter flow ----
class TestTransporter:
    @pytest.fixture(scope="class")
    def trans_token(self):
        r = requests.post(f"{API}/auth/login", json={"email": TRANS_EMAIL, "password": TRANS_PASS})
        return r.json()["access_token"]

    def test_transporter_access_device(self, trans_token):
        r = requests.post(f"{API}/transporter/access",
                          headers=auth_h(trans_token),
                          json={"device_password": DEVICE_PASS})
        assert r.status_code == 200, r.text
        assert r.json()["device_id"] == DEVICE_ID

    def test_transporter_device_details(self, trans_token):
        r = requests.get(f"{API}/transporter/device/{DEVICE_ID}", headers=auth_h(trans_token))
        assert r.status_code == 200
        d = r.json()
        assert d["device"]["device_id"] == DEVICE_ID
        assert "readings" in d and "alerts" in d

    def test_transporter_cannot_access_admin(self, trans_token):
        for ep in ["/devices", "/alerts", "/stats/summary", "/devices/pending"]:
            r = requests.get(f"{API}{ep}", headers=auth_h(trans_token))
            assert r.status_code == 403, f"{ep} -> {r.status_code}"

    def test_transporter_wrong_hw_pass(self, trans_token):
        r = requests.post(f"{API}/transporter/access",
                          headers=auth_h(trans_token),
                          json={"device_password": "WRONG_HW"})
        assert r.status_code == 401


# ---- Cleanup ----
@pytest.fixture(scope="session", autouse=True)
def cleanup(request):
    yield
    try:
        mc = MongoClient("mongodb://localhost:27017")
        db = mc["coldchain_db"]
        db.devices.delete_many({"device_id": DEVICE_ID})
        db.readings.delete_many({"device_id": DEVICE_ID})
        db.alerts.delete_many({"device_id": DEVICE_ID})
        db.events.delete_many({"device_id": DEVICE_ID})
        mc.close()
    except Exception:
        pass
