"""Semana 14 – Pruebas funcionales de RF-01 y RF-02 y verificación de RNF-01, 02, 05 y 06 con base real.

Ejecutar (backend corriendo):
    REACT_APP_BACKEND_URL=http://localhost:8001 pytest tests/test_semana14_rf.py -v
Lee MONGO_URL y DB_NAME de backend/.env para verificar la persistencia desde otra conexión.
"""
import os
import hmac
import time
import uuid
import hashlib
import threading
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
import pyotp
import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
PREFIX = f"TEST_S14_{uuid.uuid4().hex[:6]}_"
PWD = "Clave_Prueba_S14"
TRANSPORTER = ("transportador@coldchain.com", "transport123")


def dev(name):
    return PREFIX + name


def sign(password, device_id, nonce, t):
    return hmac.new(password.encode(), f"{device_id}|{nonce}|{t:.2f}".encode(), hashlib.sha256).hexdigest()


def post_temp(device_id, t, password=PWD, **extra):
    return requests.post(f"{API}/temperatura", json={"deviceId": device_id, "devicePassword": password,
                                                    "temperature": t, **extra}, timeout=15)


@pytest.fixture(scope="session")
def db():
    mc = MongoClient(os.environ["MONGO_URL"])
    database = mc[os.environ["DB_NAME"]]
    yield database
    rx = {"$regex": f"^{PREFIX}"}
    for col in ("devices", "readings", "alerts", "events"):
        database[col].delete_many({"device_id": rx})
    mc.close()


@pytest.fixture(scope="session")
def admin(db):
    email = f"qa_s14_{uuid.uuid4().hex[:6]}@coldchain.com"
    password, secret = "QaS14_Admin!", pyotp.random_base32()
    db.users.insert_one({
        "id": str(uuid.uuid4()), "email": email, "name": "QA S14", "role": "admin",
        "password_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        "must_change_password": False, "totp_enabled": True, "totp_secret": secret,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    r = requests.post(f"{API}/auth/2fa/verify", json={"temp_token": r.json()["temp_token"],
                                                      "code": pyotp.TOTP(secret).now()}, timeout=15)
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    s.email = email
    yield s
    db.users.delete_one({"email": email})


def approved_device(admin, name, secure=False):
    device_id = dev(name)
    if secure:
        r = post_temp(device_id, 5.0, nonce=1, signature=sign(PWD, device_id, 1, 5.0))
    else:
        r = post_temp(device_id, 5.0)
    assert r.status_code == 200 and r.json()["status"] == "pending"
    assert admin.post(f"{API}/devices/approve", json={"device_id": device_id}).status_code == 200
    return device_id


# ---------------- RF-01: ingesta ----------------
class TestRF01:
    def test_registro_nuevo_queda_pendiente_sin_lectura(self, db):
        d = dev("nuevo")
        r = post_temp(d, 5.0)
        assert r.status_code == 200
        assert r.json()["status"] == "pending"
        doc = db.devices.find_one({"device_id": d})
        assert doc["status"] == "pending" and doc["device_password_hash"] != PWD
        assert db.readings.count_documents({"device_id": d}) == 0

    def test_pendiente_no_persiste_lecturas(self, db):
        d = dev("pend")
        post_temp(d, 5.0)
        r = post_temp(d, 6.0)
        assert r.status_code == 200 and r.json()["status"] == "pending"
        assert db.readings.count_documents({"device_id": d}) == 0

    def test_aprobado_persiste_y_se_recupera_desde_otra_conexion(self, admin, db):
        d = approved_device(admin, "ok")
        r = post_temp(d, 5.25)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "active" and body["alert"] is None and body["reading_id"]
        other = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        saved = other.readings.find_one({"id": body["reading_id"]})
        assert saved["device_id"] == d and saved["temperature"] == 5.25
        assert other.devices.find_one({"device_id": d})["last_temperature"] == 5.25
        api_readings = admin.get(f"{API}/devices/{d}/readings").json()
        assert any(x["id"] == body["reading_id"] for x in api_readings)

    def test_device_id_unico_con_registros_simultaneos(self, db):
        d = dev("concurrente")
        codes = []

        def worker():
            codes.append(post_temp(d, 5.0).status_code)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert db.devices.count_documents({"device_id": d}) == 1
        assert set(codes) <= {200, 409}, codes

    @pytest.mark.parametrize("payload", [
        {"devicePassword": PWD, "temperature": 5.0},
        {"deviceId": "X", "temperature": 5.0},
        {"deviceId": "X", "devicePassword": PWD},
        {"deviceId": "X", "devicePassword": PWD, "temperature": "abc"},
        {"deviceId": "X", "devicePassword": PWD, "temperature": -127},
        {"deviceId": "", "devicePassword": PWD, "temperature": 5.0},
    ])
    def test_entrada_invalida_422_sin_registro(self, db, payload):
        if "deviceId" in payload and payload["deviceId"]:
            payload = {**payload, "deviceId": dev("invalido")}
        before = db.devices.count_documents({}), db.readings.count_documents({})
        r = requests.post(f"{API}/temperatura", json=payload, timeout=15)
        assert r.status_code == 422
        assert isinstance(r.json()["detail"], list)
        assert (db.devices.count_documents({}), db.readings.count_documents({})) == before

    def test_dispositivo_rechazado_403_sin_lectura(self, admin, db):
        d = dev("rechazado")
        post_temp(d, 5.0)
        assert admin.post(f"{API}/devices/reject", json={"device_id": d}).status_code == 200
        r = post_temp(d, 5.0)
        assert r.status_code == 403
        assert db.readings.count_documents({"device_id": d}) == 0

    def test_consulta_dispositivo_inexistente_404(self, admin):
        assert admin.get(f"{API}/devices/{dev('no_existe')}").status_code == 404
        assert admin.get(f"{API}/devices/{dev('no_existe')}/alerts").status_code == 404


# ---------------- RNF-01: autenticidad ----------------
def test_rnf01_password_invalida_rechazada_100(admin, db):
    d = approved_device(admin, "rnf01")
    before = db.readings.count_documents({"device_id": d})
    codes = [post_temp(d, 5.0, password=f"mala_{i}").status_code for i in range(10)]
    assert codes == [401] * 10
    assert db.readings.count_documents({"device_id": d}) == before


# ---------------- RNF-02: integridad (HMAC + nonce) ----------------
class TestRNF02:
    def test_firma_y_nonce(self, admin, db):
        d = approved_device(admin, "hmac", secure=True)
        assert db.devices.find_one({"device_id": d})["require_hmac"] is True
        ok = post_temp(d, 5.0, nonce=10, signature=sign(PWD, d, 10, 5.0))
        assert ok.status_code == 200 and ok.json()["status"] == "active"
        base = db.readings.count_documents({"device_id": d})

        bad_sig = post_temp(d, 5.0, nonce=11, signature=sign(PWD, d, 11, 5.0)[:-1] + "0")
        tampered = post_temp(d, 9.9, nonce=12, signature=sign(PWD, d, 12, 5.0))
        replay = post_temp(d, 5.0, nonce=10, signature=sign(PWD, d, 10, 5.0))
        older = post_temp(d, 5.0, nonce=3, signature=sign(PWD, d, 3, 5.0))
        missing = post_temp(d, 5.0)

        assert [bad_sig.status_code, tampered.status_code, missing.status_code] == [401, 401, 401]
        assert [replay.status_code, older.status_code] == [409, 409]
        assert db.readings.count_documents({"device_id": d}) == base
        assert db.devices.find_one({"device_id": d})["last_nonce"] == 10


# ---------------- RF-02 / RNF-05: clasificación en valores límite ----------------
@pytest.fixture(scope="module")
def boundary_device(admin):
    return approved_device(admin, "limites")


@pytest.mark.parametrize("t,expected", [
    (1.9, "critical"), (2.0, "warning"), (2.5, "warning"), (5.0, None),
    (7.5, "warning"), (8.0, "warning"), (8.1, "critical"),
])
def test_rnf05_clasificacion_limites(boundary_device, db, t, expected):
    before = db.alerts.count_documents({"device_id": boundary_device})
    r = post_temp(boundary_device, t)
    assert r.status_code == 200
    assert r.json()["alert"] == expected
    after = db.alerts.count_documents({"device_id": boundary_device})
    if expected is None:
        assert after == before
    else:
        assert after == before + 1
        last = db.alerts.find_one({"device_id": boundary_device}, sort=[("ts", -1)])
        assert last["severity"] == expected and last["temperature"] == t and last["acknowledged"] is False


# ---------------- RF-02: listar y reconocer ----------------
class TestRF02:
    def test_listar_y_reconocer(self, admin, db):
        d = approved_device(admin, "alertas")
        post_temp(d, 9.0)
        post_temp(d, 7.6)
        all_alerts = admin.get(f"{API}/alerts").json()
        mine = [a for a in all_alerts if a["device_id"] == d]
        assert sorted(a["severity"] for a in mine) == ["critical", "warning"]
        assert all("_id" not in a for a in mine)

        target = mine[0]["id"]
        r = admin.post(f"{API}/alerts/{target}/ack")
        assert r.status_code == 200 and r.json()["alert"]["acknowledged"] is True
        saved = db.alerts.find_one({"id": target})
        assert saved["acknowledged"] is True and saved["acknowledged_by"] == admin.email
        active = admin.get(f"{API}/alerts", params={"active_only": "true"}).json()
        assert target not in [a["id"] for a in active]

        r = admin.post(f"{API}/devices/{d}/alerts/ack-all")
        assert r.status_code == 200 and r.json()["count"] == 1
        assert db.alerts.count_documents({"device_id": d, "acknowledged": False}) == 0

    def test_reconocer_inexistente_404(self, admin, db):
        before = db.alerts.count_documents({"acknowledged": True})
        assert admin.post(f"{API}/alerts/{uuid.uuid4()}/ack").status_code == 404
        assert admin.post(f"{API}/devices/{dev('fantasma')}/alerts/ack-all").status_code == 404
        assert db.alerts.count_documents({"acknowledged": True}) == before

    def test_acceso_restringido(self):
        assert requests.get(f"{API}/alerts", timeout=15).status_code == 401
        r = requests.post(f"{API}/auth/login", json={"email": TRANSPORTER[0], "password": TRANSPORTER[1]}, timeout=15)
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        assert requests.get(f"{API}/alerts", headers=h, timeout=15).status_code == 403
        assert requests.post(f"{API}/alerts/{uuid.uuid4()}/ack", headers=h, timeout=15).status_code == 403


# ---------------- RNF-06: inactividad ----------------
def test_rnf06_inactivo_tras_60s(admin):
    d = approved_device(admin, "inactivo")
    assert post_temp(d, 5.0).status_code == 200
    assert admin.get(f"{API}/devices/{d}").json()["live_status"] == "active"
    time.sleep(65)
    assert admin.get(f"{API}/devices/{d}").json()["live_status"] == "inactive"
