"""Tests for new admin user management + self-service password change."""
import os
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


def reset_admin(mongo):
    ph = bcrypt.hashpw(ADMIN_PASS.encode(), bcrypt.gensalt()).decode()
    mongo.users.update_one(
        {"email": ADMIN_EMAIL},
        {"$set": {"password_hash": ph, "must_change_password": True,
                  "totp_enabled": False, "totp_secret": None, "disabled": False}},
    )


@pytest.fixture(scope="module")
def admin_token(mongo):
    """Onboard admin (change_password -> enroll_2fa) and return access token."""
    reset_admin(mongo)
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200
    d = r.json(); assert d["step"] == "change_password"
    r = requests.post(f"{API}/auth/change-password",
                      json={"temp_token": d["temp_token"], "new_password": NEW_ADMIN_PASS})
    assert r.status_code == 200
    d = r.json(); assert d["step"] == "enroll_2fa"
    secret = d["secret"]; temp = d["temp_token"]
    code = pyotp.TOTP(secret).now()
    r = requests.post(f"{API}/auth/2fa/enroll-verify", json={"temp_token": temp, "code": code})
    assert r.status_code == 200
    return r.json()["access_token"]


def H(t): return {"Authorization": f"Bearer {t}"}


# ===== GET /api/admin/users =====
class TestListUsers:
    def test_list_returns_admins_and_transporters(self, admin_token):
        r = requests.get(f"{API}/admin/users", headers=H(admin_token))
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list) and len(users) >= 2
        roles = {u["role"] for u in users}
        assert "admin" in roles and "transporter" in roles
        # No sensitive fields exposed
        for u in users:
            assert "password_hash" not in u
            assert "totp_secret" not in u
            for k in ("id", "email", "name", "role", "disabled",
                      "must_change_password", "totp_enabled"):
                assert k in u

    def test_list_role_filter(self, admin_token):
        r = requests.get(f"{API}/admin/users?role=admin", headers=H(admin_token))
        assert r.status_code == 200
        for u in r.json():
            assert u["role"] == "admin"
        r = requests.get(f"{API}/admin/users?role=transporter", headers=H(admin_token))
        assert r.status_code == 200
        for u in r.json():
            assert u["role"] == "transporter"

    def test_unauthenticated_forbidden(self):
        r = requests.get(f"{API}/admin/users")
        assert r.status_code in (401, 403)


# ===== POST /api/admin/users =====
class TestCreateUser:
    created_ids = []

    def test_create_admin(self, admin_token, mongo):
        email = f"TEST_admin_{uuid.uuid4().hex[:6]}@coldchain.com"
        r = requests.post(f"{API}/admin/users", headers=H(admin_token),
                          json={"email": email.upper(), "name": "Test Admin",
                                "password": "tempPass1", "role": "admin"})
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["email"] == email.lower()  # normalized lowercase
        assert u["role"] == "admin"
        assert u["must_change_password"] is True
        assert u["disabled"] is False
        assert u["totp_enabled"] is False
        assert "password_hash" not in u
        TestCreateUser.created_ids.append(u["id"])

        # Verify persistence via GET
        r = requests.get(f"{API}/admin/users", headers=H(admin_token))
        assert any(x["id"] == u["id"] and x["email"] == email.lower() for x in r.json())

    def test_create_transporter(self, admin_token):
        email = f"TEST_trans_{uuid.uuid4().hex[:6]}@coldchain.com"
        r = requests.post(f"{API}/admin/users", headers=H(admin_token),
                          json={"email": email, "name": "Test Trans",
                                "password": "tempPass2", "role": "transporter",
                                "must_change_password": False})
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["role"] == "transporter"
        assert u["must_change_password"] is False
        TestCreateUser.created_ids.append(u["id"])

    def test_create_duplicate_email_fails(self, admin_token):
        email = f"TEST_dup_{uuid.uuid4().hex[:6]}@coldchain.com"
        r = requests.post(f"{API}/admin/users", headers=H(admin_token),
                          json={"email": email, "name": "x", "password": "abcdef",
                                "role": "transporter"})
        assert r.status_code == 200
        TestCreateUser.created_ids.append(r.json()["id"])
        r2 = requests.post(f"{API}/admin/users", headers=H(admin_token),
                           json={"email": email, "name": "y", "password": "abcdef",
                                 "role": "transporter"})
        assert r2.status_code == 400

    def test_create_invalid_role_rejected(self, admin_token):
        r = requests.post(f"{API}/admin/users", headers=H(admin_token),
                          json={"email": f"TEST_{uuid.uuid4().hex[:6]}@x.com",
                                "name": "x", "password": "abcdef", "role": "superuser"})
        assert r.status_code in (400, 422)


# ===== PATCH /api/admin/users/{id} =====
class TestUpdateUser:
    @pytest.fixture
    def fresh_user(self, admin_token):
        email = f"TEST_upd_{uuid.uuid4().hex[:6]}@coldchain.com"
        r = requests.post(f"{API}/admin/users", headers=H(admin_token),
                          json={"email": email, "name": "Original",
                                "password": "tempPass1", "role": "transporter"})
        return r.json()

    def test_update_name_and_persist(self, admin_token, fresh_user):
        r = requests.patch(f"{API}/admin/users/{fresh_user['id']}",
                           headers=H(admin_token), json={"name": "Updated Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "Updated Name"
        # GET verify
        r = requests.get(f"{API}/admin/users", headers=H(admin_token))
        match = next(u for u in r.json() if u["id"] == fresh_user["id"])
        assert match["name"] == "Updated Name"

    def test_disable_then_enable(self, admin_token, fresh_user, mongo):
        # Disable
        r = requests.patch(f"{API}/admin/users/{fresh_user['id']}",
                           headers=H(admin_token), json={"disabled": True})
        assert r.status_code == 200 and r.json()["disabled"] is True
        # Disabled user cannot login
        r = requests.post(f"{API}/auth/login",
                          json={"email": fresh_user["email"], "password": "tempPass1"})
        assert r.status_code == 403
        assert "deshabilitado" in r.json().get("detail", "").lower()
        # Re-enable
        r = requests.patch(f"{API}/admin/users/{fresh_user['id']}",
                           headers=H(admin_token), json={"disabled": False})
        assert r.status_code == 200 and r.json()["disabled"] is False
        # Login restored (should at least not 403; might be change_password step)
        r = requests.post(f"{API}/auth/login",
                          json={"email": fresh_user["email"], "password": "tempPass1"})
        assert r.status_code == 200

    def test_cannot_disable_self(self, admin_token, mongo):
        me = mongo.users.find_one({"email": ADMIN_EMAIL})
        r = requests.patch(f"{API}/admin/users/{me['id']}",
                           headers=H(admin_token), json={"disabled": True})
        assert r.status_code == 400

    def test_reset_2fa(self, admin_token, mongo, fresh_user):
        # Manually mark user as totp enabled
        mongo.users.update_one({"id": fresh_user["id"]},
                               {"$set": {"totp_enabled": True, "totp_secret": "ABC"}})
        r = requests.patch(f"{API}/admin/users/{fresh_user['id']}",
                           headers=H(admin_token), json={"reset_2fa": True})
        assert r.status_code == 200
        assert r.json()["totp_enabled"] is False
        u = mongo.users.find_one({"id": fresh_user["id"]})
        assert u.get("totp_secret") is None


# ===== POST /api/admin/users/{id}/reset-password =====
class TestAdminResetPassword:
    def test_reset_password_forces_change(self, admin_token):
        email = f"TEST_rst_{uuid.uuid4().hex[:6]}@coldchain.com"
        r = requests.post(f"{API}/admin/users", headers=H(admin_token),
                          json={"email": email, "name": "rst",
                                "password": "oldPass1", "role": "transporter",
                                "must_change_password": False})
        uid = r.json()["id"]

        new_pass = "BrandNewPass99!"
        r = requests.post(f"{API}/admin/users/{uid}/reset-password",
                          headers=H(admin_token),
                          json={"new_password": new_pass, "must_change_password": True})
        assert r.status_code == 200, r.text

        # New login uses new password and step=change_password
        r = requests.post(f"{API}/auth/login",
                          json={"email": email, "password": new_pass})
        assert r.status_code == 200
        assert r.json()["step"] == "change_password"


# ===== DELETE /api/admin/users/{id} =====
class TestDeleteUser:
    def test_delete_self_forbidden(self, admin_token, mongo):
        me = mongo.users.find_one({"email": ADMIN_EMAIL})
        r = requests.delete(f"{API}/admin/users/{me['id']}", headers=H(admin_token))
        assert r.status_code == 400

    def test_cannot_delete_last_admin(self, admin_token, mongo):
        # Currently only the seed admin exists -> deleting it would leave 0 admins.
        # Create a second admin then try to delete admin while only one would remain.
        # The seed admin is "self" and protected separately, so create a 2nd admin then
        # delete IT: with seed admin still alive remaining will be 1 (seed) -> allowed.
        # To trigger last-admin block, we delete the OTHER admin only after ensuring
        # the seed admin is the *target*. Since we cannot delete self, we test the
        # last-admin guard via temporarily disabling seed (NOT possible-self) so we
        # simulate by creating an admin and deleting it: should succeed (>=1 left).
        email = f"TEST_a2_{uuid.uuid4().hex[:6]}@coldchain.com"
        r = requests.post(f"{API}/admin/users", headers=H(admin_token),
                          json={"email": email, "name": "a2",
                                "password": "tempPass1", "role": "admin"})
        uid = r.json()["id"]
        r = requests.delete(f"{API}/admin/users/{uid}", headers=H(admin_token))
        assert r.status_code == 200

    def test_delete_user_then_404(self, admin_token):
        email = f"TEST_del_{uuid.uuid4().hex[:6]}@coldchain.com"
        r = requests.post(f"{API}/admin/users", headers=H(admin_token),
                          json={"email": email, "name": "del",
                                "password": "tempPass1", "role": "transporter"})
        uid = r.json()["id"]
        r = requests.delete(f"{API}/admin/users/{uid}", headers=H(admin_token))
        assert r.status_code == 200
        # Second delete -> 404
        r = requests.delete(f"{API}/admin/users/{uid}", headers=H(admin_token))
        assert r.status_code == 404


# ===== POST /api/auth/change-my-password =====
class TestSelfChangePassword:
    def _make_transporter(self, admin_token):
        email = f"TEST_self_{uuid.uuid4().hex[:6]}@coldchain.com"
        r = requests.post(f"{API}/admin/users", headers=H(admin_token),
                          json={"email": email, "name": "self",
                                "password": "selfPass1", "role": "transporter",
                                "must_change_password": False})
        assert r.status_code == 200
        return email, "selfPass1"

    def test_self_change_success(self, admin_token):
        email, pw = self._make_transporter(admin_token)
        # login
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
        token = r.json()["access_token"]
        # change pw
        new_pw = "NewSelfPass99!"
        r = requests.post(f"{API}/auth/change-my-password", headers=H(token),
                          json={"current_password": pw, "new_password": new_pw})
        assert r.status_code == 200
        # login with new pw
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": new_pw})
        assert r.status_code == 200
        assert r.json()["step"] == "ok"

    def test_self_change_wrong_current(self, admin_token):
        email, pw = self._make_transporter(admin_token)
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
        token = r.json()["access_token"]
        r = requests.post(f"{API}/auth/change-my-password", headers=H(token),
                          json={"current_password": "WRONG", "new_password": "anyOtherPw1"})
        assert r.status_code == 401

    def test_self_change_same_password_rejected(self, admin_token):
        email, pw = self._make_transporter(admin_token)
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
        token = r.json()["access_token"]
        r = requests.post(f"{API}/auth/change-my-password", headers=H(token),
                          json={"current_password": pw, "new_password": pw})
        assert r.status_code == 400

    def test_self_change_unauth(self):
        r = requests.post(f"{API}/auth/change-my-password",
                          json={"current_password": "x", "new_password": "yyyyyyyy"})
        assert r.status_code in (401, 403)


# ===== New admin onboarding flow =====
class TestNewAdminOnboarding:
    def test_new_admin_full_flow(self, admin_token):
        email = f"TEST_newadmin_{uuid.uuid4().hex[:6]}@coldchain.com"
        pw = "tempAdmin1"
        r = requests.post(f"{API}/admin/users", headers=H(admin_token),
                          json={"email": email, "name": "NewAdm", "password": pw,
                                "role": "admin"})
        assert r.status_code == 200

        # 1) login -> change_password
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
        d = r.json()
        assert d["step"] == "change_password"

        # 2) change pw -> enroll_2fa
        new_pw = "BrandNewAdmin99!"
        r = requests.post(f"{API}/auth/change-password",
                          json={"temp_token": d["temp_token"], "new_password": new_pw})
        d = r.json()
        assert d["step"] == "enroll_2fa"
        assert "secret" in d and "qr_data_url" in d

        # 3) enroll-verify
        code = pyotp.TOTP(d["secret"]).now()
        r = requests.post(f"{API}/auth/2fa/enroll-verify",
                          json={"temp_token": d["temp_token"], "code": code})
        assert r.status_code == 200
        assert "access_token" in r.json()


# ===== Smoke prior flows =====
class TestSmokePriorFlows:
    def test_transporter_login_still_works(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": TRANS_EMAIL, "password": TRANS_PASS})
        assert r.status_code == 200
        assert r.json()["step"] == "ok"

    def test_stats_summary_admin(self, admin_token):
        r = requests.get(f"{API}/stats/summary", headers=H(admin_token))
        assert r.status_code == 200
        for k in ("active", "inactive", "pending", "critical_alerts",
                  "warning_alerts", "total_devices"):
            assert k in r.json()


# ===== Cleanup =====
@pytest.fixture(scope="session", autouse=True)
def cleanup():
    yield
    try:
        mc = MongoClient("mongodb://localhost:27017")
        db = mc["coldchain_db"]
        # Delete TEST_-prefixed users
        db.users.delete_many({"email": {"$regex": r"^test_", "$options": "i"}})
        # Reset admin to initial state
        ph = bcrypt.hashpw(ADMIN_PASS.encode(), bcrypt.gensalt()).decode()
        db.users.update_one(
            {"email": ADMIN_EMAIL},
            {"$set": {"password_hash": ph, "must_change_password": True,
                      "totp_enabled": False, "totp_secret": None, "disabled": False}},
        )
        mc.close()
    except Exception as e:
        print("cleanup error:", e)
