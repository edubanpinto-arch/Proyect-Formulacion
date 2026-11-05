"""Email alerts feature: alert_state transitions, alert.email_* audit, /admin/email/* endpoints."""
import os
import time
import uuid
import pytest
import pyotp
import bcrypt
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
TRANS_EMAIL = "transportador@coldchain.com"
TRANS_PASS = "transport123"
DEV_ID = f"TEST_EMAIL_DEV_{uuid.uuid4().hex[:6]}"
DEV_PASS = "TEST_DEV_PASS_1"
TA_EMAIL = f"test_email_admin_{uuid.uuid4().hex[:6]}@example.com"
TA_PASS = "TestAdmin!2345"
TA_SECRET = pyotp.random_base32()


@pytest.fixture(scope="module")
def mongo():
    mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    yield mc["coldchain_db"]
    mc.close()


@pytest.fixture(scope="module")
def admin_token(mongo):
    # fresh test admin (do not touch the real admin)
    uid = str(uuid.uuid4())
    mongo.users.insert_one({
        "id": uid, "email": TA_EMAIL, "name": "TEST_EmailAdmin", "role": "admin",
        "password_hash": bcrypt.hashpw(TA_PASS.encode(), bcrypt.gensalt()).decode(),
        "must_change_password": False, "totp_enabled": True, "totp_secret": TA_SECRET,
        "created_at": "2026-01-01T00:00:00+00:00", "disabled": False,
    })
    r = requests.post(f"{API}/auth/login", json={"email": TA_EMAIL, "password": TA_PASS})
    assert r.status_code == 200, r.text
    d = r.json(); assert d["step"] == "verify_2fa"
    r = requests.post(f"{API}/auth/2fa/verify",
                      json={"temp_token": d["temp_token"], "code": pyotp.TOTP(TA_SECRET).now()})
    assert r.status_code == 200, r.text
    yield r.json()["access_token"]
    mongo.users.delete_one({"id": uid})


@pytest.fixture(scope="module")
def trans_token():
    r = requests.post(f"{API}/auth/login", json={"email": TRANS_EMAIL, "password": TRANS_PASS})
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def device(mongo, admin_token):
    r = requests.post(f"{API}/temperatura", json={"deviceId": DEV_ID, "devicePassword": DEV_PASS, "temperature": 5.0})
    assert r.status_code == 200 and r.json()["status"] == "pending"
    r = requests.post(f"{API}/devices/approve", headers={"Authorization": f"Bearer {admin_token}"},
                      json={"device_id": DEV_ID, "transporter_email": TRANS_EMAIL})
    assert r.status_code == 200, r.text
    yield DEV_ID
    for c in ("devices", "readings", "alerts", "events"):
        mongo[c].delete_many({"device_id": DEV_ID})
    mongo.audit_log.delete_many({"target_id": DEV_ID})


def ingest(t):
    s = time.time()
    r = requests.post(f"{API}/temperatura", json={"deviceId": DEV_ID, "devicePassword": DEV_PASS, "temperature": t})
    return r, time.time() - s


def wait_audit(mongo, n, timeout=40):
    end = time.time() + timeout
    while time.time() < end:
        docs = list(mongo.audit_log.find({"target_id": DEV_ID, "action": {"$regex": "^alert.email"}},
                                         {"_id": 0}).sort("ts", 1))
        if len(docs) >= n:
            return docs
        time.sleep(1)
    return list(mongo.audit_log.find({"target_id": DEV_ID, "action": {"$regex": "^alert.email"}},
                                     {"_id": 0}).sort("ts", 1))


def state(mongo):
    return mongo.devices.find_one({"device_id": DEV_ID}).get("alert_state", "normal")


# --- Transition sequence & audit entries ---
class TestTransitions:
    def test_full_sequence(self, mongo, device):
        # (temp, expected_state, expect_new_email)
        seq = [
            (5.0, "normal", False),
            (7.8, "warning", True),    # normal->warning
            (7.9, "warning", False),   # repeat
            (10.0, "critical", True),  # warning->critical
            (11.0, "critical", False), # repeat
            (2.3, "warning", False),   # critical->warning de-escalation: no email
            (5.0, "normal", True),     # ->normal
            (5.5, "normal", False),    # repeat
            (1.0, "critical", True),   # normal->critical
            (5.0, "normal", True),     # ->normal
        ]
        expected = 0
        expected_states = []
        for t, st, em in seq:
            r, dt = ingest(t)
            assert r.status_code == 200, r.text
            assert dt < 5, f"ingest too slow {dt:.1f}s"
            assert state(mongo) == st, f"after {t} expected {st}, got {state(mongo)}"
            if em:
                expected += 1
                expected_states.append(st)
                docs = wait_audit(mongo, expected)
                assert len(docs) == expected, f"after {t}: {len(docs)} audit entries, expected {expected}"
            else:
                time.sleep(3)
                docs = wait_audit(mongo, expected, timeout=0)
                assert len(docs) == expected, f"unexpected email audit after {t}: {docs[-1] if docs else None}"
        docs = wait_audit(mongo, expected, timeout=5)
        assert [d["metadata"]["state"] for d in docs] == expected_states
        for d in docs:
            assert d["action"] in ("alert.email_sent", "alert.email_failed")
            assert d["actor_email"] == "system"
            assert d["target_type"] == "device"
            if d["action"] == "alert.email_failed":
                assert d["success"] is False and d["metadata"].get("error")
            else:
                assert TRANS_EMAIL in d["metadata"]["recipients"]
        print("AUDIT:", [(d["action"], d["metadata"]) for d in docs])


# --- /admin/email endpoints ---
class TestEmailEndpoints:
    def test_status_admin(self, admin_token):
        r = requests.get(f"{API}/admin/email/status", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        d = r.json()
        assert d["configured"] is True and "sender" in d
        print("STATUS:", d)

    def test_status_noauth(self):
        assert requests.get(f"{API}/admin/email/status").status_code in (401, 403)

    def test_status_transporter(self, trans_token):
        r = requests.get(f"{API}/admin/email/status", headers={"Authorization": f"Bearer {trans_token}"})
        assert r.status_code == 403

    def test_test_email_noauth(self):
        assert requests.post(f"{API}/admin/email/test").status_code in (401, 403)

    def test_test_email_transporter(self, trans_token):
        r = requests.post(f"{API}/admin/email/test", headers={"Authorization": f"Bearer {trans_token}"})
        assert r.status_code == 403

    def test_test_email_invalid_creds(self, admin_token, mongo):
        r = requests.post(f"{API}/admin/email/test", headers={"Authorization": f"Bearer {admin_token}"}, timeout=60)
        print("TEST EMAIL:", r.status_code, r.text)
        assert r.status_code == 502
        assert r.json()["detail"].startswith("No se pudo enviar el correo")
        a = mongo.audit_log.find_one({"action": "alert.email_test", "actor_email": TA_EMAIL}, {"_id": 0})
        assert a and a["success"] is False and a["metadata"].get("error")
