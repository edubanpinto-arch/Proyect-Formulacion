"""Iteration 4: unassign transporter, transporter multi-device unlock, alerts ack-all per device."""
import os
import uuid
import pyotp
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
QA_ADMIN = ("qa_admin@coldchain.com", "QaAdmin123!", "FJ7WS2VVIJ5YMZO4JPIQFG2UV75DZPR6")
TRANS = ("transportador@coldchain.com", "transport123")
SUF = uuid.uuid4().hex[:6].upper()
DEV_A, PW_A = f"TEST_MD_A_{SUF}", f"PWA_{SUF}"
DEV_B, PW_B = f"TEST_MD_B_{SUF}", f"PWB_{SUF}"
DEV_C, PW_C = f"TEST_MD_C_{SUF}", f"PWC_{SUF}"  # unassigned -> auto-assign
DEV_D, PW_D = f"TEST_MD_D_{SUF}", f"PWD_{SUF}"  # assigned to other transporter
OTHER_T = (f"test_other_{SUF.lower()}@coldchain.com", "OtherT123!")
CREATED = {"devices": [DEV_A, DEV_B, DEV_C, DEV_D], "users": []}


def _admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": QA_ADMIN[0], "password": QA_ADMIN[1]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["step"] == "verify_2fa"
    r2 = requests.post(f"{API}/auth/2fa/verify", json={"temp_token": d["temp_token"], "code": pyotp.TOTP(QA_ADMIN[2]).now()})
    assert r2.status_code == 200, r2.text
    return r2.json()["access_token"]


def _login_plain(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin():
    return _admin_token()


@pytest.fixture(scope="module", autouse=True)
def setup_devices(admin):
    for dev, pw in [(DEV_A, PW_A), (DEV_B, PW_B), (DEV_C, PW_C), (DEV_D, PW_D)]:
        r = requests.post(f"{API}/temperatura", json={"deviceId": dev, "devicePassword": pw, "temperature": 5.0})
        assert r.status_code == 200 and r.json()["status"] == "pending"
    r = requests.post(f"{API}/admin/users", headers=H(admin), json={
        "email": OTHER_T[0], "name": "TEST other", "role": "transporter", "password": OTHER_T[1], "must_change_password": False})
    assert r.status_code == 200, r.text
    CREATED["users"].append(r.json()["id"])
    yield
    # cleanup only our records
    for uid in CREATED["users"]:
        requests.delete(f"{API}/admin/users/{uid}", headers=H(admin))
    mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = mc["coldchain_db"]
    for dev in CREATED["devices"]:
        db.devices.delete_one({"device_id": dev})
        db.readings.delete_many({"device_id": dev})
        db.alerts.delete_many({"device_id": dev})
        db.events.delete_many({"device_id": dev})
    db.users.update_one({"email": TRANS[0]}, {"$pull": {"unlocked_devices": {"$in": CREATED["devices"]}}})
    mc.close()


def _dev(admin, dev):
    r = requests.get(f"{API}/devices/{dev}", headers=H(admin))
    assert r.status_code == 200
    return r.json()


# ---- Unassign bug fix ----
class TestAssign:
    def test_assign_omit_unassign(self, admin):
        r = requests.post(f"{API}/devices/approve", headers=H(admin), json={"device_id": DEV_A, "transporter_email": TRANS[0]})
        assert r.status_code == 200
        assert _dev(admin, DEV_A)["transporter_email"] == TRANS[0]
        # omitted -> unchanged
        r = requests.post(f"{API}/devices/approve", headers=H(admin), json={"device_id": DEV_A})
        assert r.status_code == 200
        assert _dev(admin, DEV_A)["transporter_email"] == TRANS[0]
        # empty -> null
        r = requests.post(f"{API}/devices/approve", headers=H(admin), json={"device_id": DEV_A, "transporter_email": ""})
        assert r.status_code == 200
        d = _dev(admin, DEV_A)
        assert d["transporter_email"] is None
        assert d["status"] == "approved"


# ---- Transporter multi-device ----
class TestTransporterMulti:
    def test_flow(self, admin):
        for dev in (DEV_A, DEV_B):
            r = requests.post(f"{API}/devices/approve", headers=H(admin), json={"device_id": dev, "transporter_email": TRANS[0]})
            assert r.status_code == 200
        requests.post(f"{API}/devices/approve", headers=H(admin), json={"device_id": DEV_C, "transporter_email": ""})
        requests.post(f"{API}/devices/approve", headers=H(admin), json={"device_id": DEV_D, "transporter_email": OTHER_T[0]})

        tok = _login_plain(*TRANS)
        r = requests.get(f"{API}/transporter/devices", headers=H(tok))
        assert r.status_code == 200
        d = r.json()
        assert d["devices"] == [], "login should reset unlocked list"
        base_total = d["assigned_total"]
        assert base_total >= 2

        # assigned but locked -> 403
        assert requests.get(f"{API}/transporter/device/{DEV_A}", headers=H(tok)).status_code == 403

        r = requests.post(f"{API}/transporter/access", headers=H(tok), json={"device_password": PW_A})
        assert r.status_code == 200 and r.json()["device_id"] == DEV_A
        assert "device_password_hash" not in r.json()
        d = requests.get(f"{API}/transporter/devices", headers=H(tok)).json()
        assert [x["device_id"] for x in d["devices"]] == [DEV_A]
        assert requests.get(f"{API}/transporter/device/{DEV_A}", headers=H(tok)).status_code == 200
        assert requests.get(f"{API}/transporter/device/{DEV_B}", headers=H(tok)).status_code == 403

        r = requests.post(f"{API}/transporter/access", headers=H(tok), json={"device_password": PW_B})
        assert r.status_code == 200 and r.json()["device_id"] == DEV_B
        d = requests.get(f"{API}/transporter/devices", headers=H(tok)).json()
        assert {x["device_id"] for x in d["devices"]} == {DEV_A, DEV_B}
        assert requests.get(f"{API}/transporter/device/{DEV_B}", headers=H(tok)).status_code == 200

        # re-entering same password is idempotent
        r = requests.post(f"{API}/transporter/access", headers=H(tok), json={"device_password": PW_A})
        assert r.status_code == 200
        assert len(requests.get(f"{API}/transporter/devices", headers=H(tok)).json()["devices"]) == 2

        # unassigned approved -> auto-assign
        r = requests.post(f"{API}/transporter/access", headers=H(tok), json={"device_password": PW_C})
        assert r.status_code == 200 and r.json()["device_id"] == DEV_C
        assert _dev(admin, DEV_C)["transporter_email"] == TRANS[0]
        d = requests.get(f"{API}/transporter/devices", headers=H(tok)).json()
        assert d["assigned_total"] == base_total + 1
        assert len(d["devices"]) == 3

        # other transporter's device -> 401
        r = requests.post(f"{API}/transporter/access", headers=H(tok), json={"device_password": PW_D})
        assert r.status_code == 401
        assert requests.get(f"{API}/transporter/device/{DEV_D}", headers=H(tok)).status_code == 403
        # wrong pwd
        assert requests.post(f"{API}/transporter/access", headers=H(tok), json={"device_password": "nope"}).status_code == 401

        # other transporter can unlock D
        tok2 = _login_plain(*OTHER_T)
        r = requests.post(f"{API}/transporter/access", headers=H(tok2), json={"device_password": PW_D})
        assert r.status_code == 200 and r.json()["device_id"] == DEV_D
        assert requests.get(f"{API}/transporter/device/{DEV_A}", headers=H(tok2)).status_code == 403

        # unassign A -> disappears from transporter list, detail 403
        requests.post(f"{API}/devices/approve", headers=H(admin), json={"device_id": DEV_A, "transporter_email": ""})
        d = requests.get(f"{API}/transporter/devices", headers=H(tok)).json()
        assert DEV_A not in [x["device_id"] for x in d["devices"]]
        assert requests.get(f"{API}/transporter/device/{DEV_A}", headers=H(tok)).status_code == 403

        # re-login resets
        tok = _login_plain(*TRANS)
        assert requests.get(f"{API}/transporter/devices", headers=H(tok)).json()["devices"] == []


# ---- Alerts ack-all ----
class TestAckAll:
    def test_ack_all(self, admin):
        requests.post(f"{API}/devices/approve", headers=H(admin), json={"device_id": DEV_B})
        sevs = []
        for t in (9.5, 10.0, 1.0, 7.8, 5.0):
            r = requests.post(f"{API}/temperatura", json={"deviceId": DEV_B, "devicePassword": PW_B, "temperature": t})
            assert r.status_code == 200
            sevs.append(r.json()["alert"])
        assert sevs == ["critical", "critical", "critical", "warning", None]
        al = requests.get(f"{API}/devices/{DEV_B}/alerts", headers=H(admin)).json()
        assert len(al) == 4 and all(not a["acknowledged"] for a in al)

        # transporter forbidden
        ttok = _login_plain(*TRANS)
        assert requests.post(f"{API}/devices/{DEV_B}/alerts/ack-all", headers=H(ttok)).status_code == 403
        # single ack
        r = requests.post(f"{API}/alerts/{al[0]['id']}/ack", headers=H(admin))
        assert r.status_code == 200
        r = requests.post(f"{API}/devices/{DEV_B}/alerts/ack-all", headers=H(admin))
        assert r.status_code == 200 and r.json()["count"] == 3
        al = requests.get(f"{API}/devices/{DEV_B}/alerts", headers=H(admin)).json()
        assert all(a["acknowledged"] for a in al)
        r = requests.post(f"{API}/devices/{DEV_B}/alerts/ack-all", headers=H(admin))
        assert r.json()["count"] == 0
        # other devices untouched check: ack-all on unknown device
        r = requests.post(f"{API}/devices/NOPE_{SUF}/alerts/ack-all", headers=H(admin))
        print("ack-all unknown device:", r.status_code, r.text)


# ---- Regression ----
class TestRegression:
    def test_admin_endpoints(self, admin):
        for p in ("/stats/summary", "/devices", "/alerts", "/admin/users"):
            r = requests.get(f"{API}{p}", headers=H(admin))
            assert r.status_code == 200, p
        s = requests.get(f"{API}/stats/summary", headers=H(admin)).json()
        assert "active" in s and "critical_alerts" in s
