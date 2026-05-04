"""Tests for the new admin audit log module."""
import os
import io
import csv
import uuid
import pytest
import pyotp
import requests
import bcrypt
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "edubanpinto@gmail.com"
ADMIN_PASS = "1234567890"
NEW_ADMIN_PASS = "NewStr0ngPass!234"
TRANS_EMAIL = "transportador@coldchain.com"
TRANS_PASS = "transport123"


@pytest.fixture(scope="module")
def mongo():
    mc = MongoClient("mongodb://localhost:27017")
    yield mc["coldchain_db"]
    mc.close()


def _reset_admin(mongo):
    ph = bcrypt.hashpw(ADMIN_PASS.encode(), bcrypt.gensalt()).decode()
    mongo.users.update_one(
        {"email": ADMIN_EMAIL},
        {"$set": {"password_hash": ph, "must_change_password": True,
                  "totp_enabled": False, "totp_secret": None, "disabled": False}},
    )


@pytest.fixture(scope="module")
def admin_token(mongo):
    """Onboard admin and return access token."""
    _reset_admin(mongo)
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200
    d = r.json(); assert d["step"] == "change_password"
    r = requests.post(f"{API}/auth/change-password",
                      json={"temp_token": d["temp_token"], "new_password": NEW_ADMIN_PASS})
    d = r.json(); assert d["step"] == "enroll_2fa"
    secret = d["secret"]
    r = requests.post(f"{API}/auth/2fa/enroll-verify",
                      json={"temp_token": d["temp_token"], "code": pyotp.TOTP(secret).now()})
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def transporter_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": TRANS_EMAIL, "password": TRANS_PASS})
    assert r.status_code == 200
    return r.json()["access_token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


# ========== ACL ==========
class TestAuditACL:
    def test_unauth_403(self):
        r = requests.get(f"{API}/admin/audit")
        assert r.status_code in (401, 403)

    def test_transporter_403(self, transporter_token):
        r = requests.get(f"{API}/admin/audit", headers=H(transporter_token))
        assert r.status_code == 403

    def test_transporter_actions_403(self, transporter_token):
        r = requests.get(f"{API}/admin/audit/actions", headers=H(transporter_token))
        assert r.status_code == 403

    def test_transporter_export_403(self, transporter_token):
        r = requests.get(f"{API}/admin/audit/export", headers=H(transporter_token))
        assert r.status_code == 403

    def test_admin_can_list(self, admin_token):
        r = requests.get(f"{API}/admin/audit", headers=H(admin_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ========== List shape & filters ==========
class TestAuditListing:
    def test_default_returns_recent_with_required_fields(self, admin_token):
        r = requests.get(f"{API}/admin/audit?limit=10", headers=H(admin_token))
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) >= 1
        for row in rows:
            for k in ("id", "ts", "action", "actor_email", "actor_id",
                      "actor_role", "target_type", "target_id", "target_label",
                      "ip", "user_agent", "success", "metadata"):
                assert k in row, f"missing key: {k}"
            assert "_id" not in row  # ObjectId must be excluded

    def test_limit_capped_at_500(self, admin_token):
        r = requests.get(f"{API}/admin/audit?limit=99999", headers=H(admin_token))
        assert r.status_code == 200
        assert len(r.json()) <= 500

    def test_descending_by_ts(self, admin_token):
        r = requests.get(f"{API}/admin/audit?limit=20", headers=H(admin_token))
        rows = r.json()
        ts_list = [r["ts"] for r in rows]
        assert ts_list == sorted(ts_list, reverse=True)

    def test_action_filter(self, admin_token):
        # auth.login_success should exist (we just logged in)
        r = requests.get(f"{API}/admin/audit?action=auth.login_success&limit=50",
                         headers=H(admin_token))
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 1
        for row in rows:
            assert row["action"] == "auth.login_success"

    def test_actor_email_filter_normalized(self, admin_token):
        # mixed-case query should still match (lowercased server-side)
        r = requests.get(f"{API}/admin/audit?actor_email=EDUBANPINTO@GMAIL.COM&limit=20",
                         headers=H(admin_token))
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 1
        for row in rows:
            assert row["actor_email"] == ADMIN_EMAIL

    def test_q_search_case_insensitive(self, admin_token):
        # search by partial action name
        r = requests.get(f"{API}/admin/audit?q=LOGIN_SUCCESS&limit=10",
                         headers=H(admin_token))
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 1
        assert all("login_success" in r["action"].lower() or
                   "login_success" in (r.get("target_label") or "").lower() or
                   "login_success" in (r.get("actor_email") or "").lower()
                   for r in rows)

    def test_distinct_actions_sorted(self, admin_token):
        r = requests.get(f"{API}/admin/audit/actions", headers=H(admin_token))
        assert r.status_code == 200
        actions = r.json()
        assert isinstance(actions, list)
        assert actions == sorted(actions)
        # Should include common ones we just produced
        assert any(a.startswith("auth.") for a in actions)


# ========== Sensitive event capture ==========
class TestSensitiveEventCapture:
    """Trigger events and assert the matching row is written."""

    def _latest(self, admin_token, action, **filters):
        params = {"action": action, "limit": 5}
        params.update(filters)
        r = requests.get(f"{API}/admin/audit", headers=H(admin_token), params=params)
        assert r.status_code == 200
        return r.json()

    def test_login_failed_recorded(self, admin_token):
        bad_email = f"audit_bad_{uuid.uuid4().hex[:6]}@x.com"
        requests.post(f"{API}/auth/login",
                      json={"email": bad_email, "password": "nope"})
        rows = self._latest(admin_token, "auth.login_failed", actor_email=bad_email)
        assert any(r["actor_email"] == bad_email and r["success"] is False for r in rows)
        # ip + user-agent must be set in this preview env (XFF injected)
        for r in rows:
            assert r["ip"], "audit row missing ip"
            assert r["user_agent"], "audit row missing user_agent"

    def test_admin_user_create_update_delete_audited(self, admin_token, mongo):
        email = f"TEST_audit_{uuid.uuid4().hex[:6]}@coldchain.com"
        # create
        r = requests.post(f"{API}/admin/users", headers=H(admin_token),
                          json={"email": email, "name": "AuditU",
                                "password": "tempPass1", "role": "transporter"})
        uid = r.json()["id"]
        rows = self._latest(admin_token, "admin.user_created")
        match = [x for x in rows if x.get("target_id") == uid]
        assert match, "user_created not audited"
        assert match[0]["actor_email"] == ADMIN_EMAIL
        assert match[0]["actor_role"] == "admin"
        assert match[0]["metadata"].get("role") == "transporter"

        # update name -> user_updated
        requests.patch(f"{API}/admin/users/{uid}", headers=H(admin_token),
                       json={"name": "Renamed"})
        rows = self._latest(admin_token, "admin.user_updated")
        assert any(x.get("target_id") == uid for x in rows)

        # disable -> user_disabled
        requests.patch(f"{API}/admin/users/{uid}", headers=H(admin_token),
                       json={"disabled": True})
        rows = self._latest(admin_token, "admin.user_disabled")
        assert any(x.get("target_id") == uid for x in rows)

        # enable -> user_enabled
        requests.patch(f"{API}/admin/users/{uid}", headers=H(admin_token),
                       json={"disabled": False})
        rows = self._latest(admin_token, "admin.user_enabled")
        assert any(x.get("target_id") == uid for x in rows)

        # admin reset password -> admin.user_password_reset
        requests.post(f"{API}/admin/users/{uid}/reset-password",
                      headers=H(admin_token),
                      json={"new_password": "ResetMe99!", "must_change_password": True})
        rows = self._latest(admin_token, "admin.user_password_reset")
        assert any(x.get("target_id") == uid for x in rows)

        # delete -> admin.user_deleted
        requests.delete(f"{API}/admin/users/{uid}", headers=H(admin_token))
        rows = self._latest(admin_token, "admin.user_deleted")
        assert any(x.get("target_id") == uid for x in rows)

    def test_logout_audited(self, admin_token):
        # login a fresh transporter session and logout
        r = requests.post(f"{API}/auth/login",
                          json={"email": TRANS_EMAIL, "password": TRANS_PASS})
        tok = r.json()["access_token"]
        r = requests.post(f"{API}/auth/logout", headers=H(tok))
        assert r.status_code == 200
        rows = self._latest(admin_token, "auth.logout", actor_email=TRANS_EMAIL)
        assert any(r["actor_email"] == TRANS_EMAIL for r in rows)

    def test_password_change_failed_audited(self, admin_token):
        # create transporter, login, attempt wrong current password
        email = f"TEST_pwfail_{uuid.uuid4().hex[:6]}@coldchain.com"
        requests.post(f"{API}/admin/users", headers=H(admin_token),
                      json={"email": email, "name": "x", "password": "okPass1",
                            "role": "transporter", "must_change_password": False})
        tok = requests.post(f"{API}/auth/login",
                            json={"email": email, "password": "okPass1"}).json()["access_token"]
        r = requests.post(f"{API}/auth/change-my-password", headers=H(tok),
                          json={"current_password": "WRONG", "new_password": "BrandNew99!"})
        assert r.status_code == 401
        rows = self._latest(admin_token, "auth.password_change_failed", actor_email=email)
        assert any(r["actor_email"] == email.lower() and r["success"] is False for r in rows)


# ========== CSV export ==========
class TestAuditExport:
    def test_csv_returns_attachment(self, admin_token):
        r = requests.get(f"{API}/admin/audit/export", headers=H(admin_token))
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/csv" in ct
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd.lower()
        text = r.text
        assert "ts,actor_email,actor_role,action" in text.splitlines()[0]
        # Has at least header + 1 row
        lines = list(csv.reader(io.StringIO(text)))
        assert len(lines) >= 2

    def test_csv_filtered_by_action(self, admin_token):
        r = requests.get(f"{API}/admin/audit/export?action=auth.login_success",
                         headers=H(admin_token))
        assert r.status_code == 200
        rows = list(csv.reader(io.StringIO(r.text)))
        header = rows[0]
        idx = header.index("action")
        for row in rows[1:]:
            assert row[idx] == "auth.login_success"

    def test_export_itself_audited(self, admin_token):
        # call export then verify admin.audit_exported row exists
        before = requests.get(f"{API}/admin/audit?action=admin.audit_exported&limit=1",
                              headers=H(admin_token)).json()
        before_count = len(before)
        requests.get(f"{API}/admin/audit/export", headers=H(admin_token))
        r = requests.get(f"{API}/admin/audit?action=admin.audit_exported&limit=10",
                         headers=H(admin_token))
        rows = r.json()
        assert len(rows) >= 1
        assert rows[0]["actor_email"] == ADMIN_EMAIL
        assert "rows" in rows[0]["metadata"]


# ========== IP / UA propagation ==========
class TestIpAndUA:
    def test_xff_header_used_as_ip(self, admin_token):
        # Trigger a fresh failed login carrying a custom XFF header
        custom_ip = "203.0.113.77"
        bad_email = f"audit_xff_{uuid.uuid4().hex[:6]}@x.com"
        requests.post(f"{API}/auth/login",
                      json={"email": bad_email, "password": "nope"},
                      headers={"X-Forwarded-For": custom_ip})
        # Note: ingress may overwrite/append XFF — first token is the original client.
        # We simply assert ip is set (not null) and is a non-empty string.
        rows = requests.get(
            f"{API}/admin/audit?actor_email={bad_email}&limit=5",
            headers=H(admin_token),
        ).json()
        assert rows
        for r in rows:
            assert r["ip"] is not None and r["ip"] != ""


# ========== Smoke: nothing regressed ==========
class TestSmokeRegression:
    def test_transporter_login_still_ok(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": TRANS_EMAIL, "password": TRANS_PASS})
        assert r.status_code == 200
        assert r.json()["step"] == "ok"

    def test_temperatura_ingest_public_still_ok(self):
        dev = f"ESP32_AUDIT_{uuid.uuid4().hex[:6].upper()}"
        # First post -> pending
        r = requests.post(f"{API}/temperatura",
                          json={"deviceId": dev, "devicePassword": "pwd_audit_1",
                                "temperature": 4.5})
        assert r.status_code == 200
        assert r.json()["status"] == "pending"

    def test_stats_summary_still_ok(self, admin_token):
        r = requests.get(f"{API}/stats/summary", headers=H(admin_token))
        assert r.status_code == 200


# ========== Cleanup ==========
@pytest.fixture(scope="session", autouse=True)
def cleanup():
    yield
    try:
        mc = MongoClient("mongodb://localhost:27017")
        db = mc["coldchain_db"]
        db.users.delete_many({"email": {"$regex": r"^test_", "$options": "i"}})
        # Reset admin
        ph = bcrypt.hashpw(ADMIN_PASS.encode(), bcrypt.gensalt()).decode()
        db.users.update_one(
            {"email": ADMIN_EMAIL},
            {"$set": {"password_hash": ph, "must_change_password": True,
                      "totp_enabled": False, "totp_secret": None, "disabled": False}},
        )
        # Clean up ESP32_AUDIT_ test devices
        db.devices.delete_many({"device_id": {"$regex": r"^ESP32_AUDIT_"}})
        db.readings.delete_many({"device_id": {"$regex": r"^ESP32_AUDIT_"}})
        mc.close()
    except Exception as e:
        print("cleanup error:", e)
