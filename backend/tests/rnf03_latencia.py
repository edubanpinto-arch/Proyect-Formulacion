"""RNF-03 – Latencia p95 de POST /api/temperatura (umbral: <= 500 ms).

Uso (backend corriendo y MongoDB local):
    python tests/rnf03_latencia.py --base-url http://localhost:8001 --n 100 --out ../documentacion/evidencias/rnf03_latencia.json
Mide la respuesta HTTP completa desde el cliente (requests, conexión persistente) para N lecturas
consecutivas de un dispositivo aprobado. Crea y elimina su propio dispositivo y usuario administrador.
"""
import os
import sys
import json
import time
import uuid
import platform
import argparse
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
import pyotp
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def percentile(values, p):
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(p / 100 * len(s) + 0.5)) - 1))
    return s[k]


def admin_session(api, db):
    email, pwd, secret = f"qa_rnf03_{uuid.uuid4().hex[:6]}@coldchain.com", "QaRnf03!", pyotp.random_base32()
    db.users.insert_one({"id": str(uuid.uuid4()), "email": email, "name": "QA RNF03", "role": "admin",
                         "password_hash": bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
                         "must_change_password": False, "totp_enabled": True, "totp_secret": secret,
                         "created_at": datetime.now(timezone.utc).isoformat()})
    tmp = requests.post(f"{api}/auth/login", json={"email": email, "password": pwd}).json()["temp_token"]
    tok = requests.post(f"{api}/auth/2fa/verify", json={"temp_token": tmp, "code": pyotp.TOTP(secret).now()}).json()
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok['access_token']}"
    return s, email


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--threshold-ms", type=float, default=500)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    api = args.base_url.rstrip("/") + "/api"
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    admin, admin_email = admin_session(api, db)
    device_id, pwd = f"TEST_RNF03_{uuid.uuid4().hex[:6]}", "Clave_RNF03"
    client = requests.Session()
    try:
        client.post(f"{api}/temperatura", json={"deviceId": device_id, "devicePassword": pwd, "temperature": 5.0})
        admin.post(f"{api}/devices/approve", json={"device_id": device_id})
        client.post(f"{api}/temperatura", json={"deviceId": device_id, "devicePassword": pwd, "temperature": 5.0})

        samples = []
        for i in range(args.n):
            t0 = time.perf_counter()
            r = client.post(f"{api}/temperatura",
                            json={"deviceId": device_id, "devicePassword": pwd, "temperature": 5.0 + (i % 10) / 10})
            ms = (time.perf_counter() - t0) * 1000
            samples.append({"i": i + 1, "status": r.status_code, "ms": round(ms, 2)})

        times = [s["ms"] for s in samples]
        ok_codes = sum(1 for s in samples if s["status"] == 200)
        p95 = percentile(times, 95)
        result = {
            "rnf": "RNF-03", "endpoint": "POST /api/temperatura", "n": args.n,
            "threshold_ms_p95": args.threshold_ms,
            "p50_ms": round(statistics.median(times), 2), "p95_ms": round(p95, 2),
            "max_ms": round(max(times), 2), "min_ms": round(min(times), 2),
            "mean_ms": round(statistics.mean(times), 2), "http_200": ok_codes,
            "cumple": p95 <= args.threshold_ms and ok_codes == args.n,
            "readings_persistidas": db.readings.count_documents({"device_id": device_id}),
            "entorno": {
                "fecha_utc": datetime.now(timezone.utc).isoformat(), "base_url": args.base_url,
                "python": sys.version.split()[0], "so": platform.platform(),
                "cpu": platform.processor() or platform.machine(), "cpus": os.cpu_count(),
                "mongodb": db.client.server_info().get("version"),
                "fastapi": __import__("fastapi").__version__,
                "medicion": "respuesta HTTP completa desde el cliente, conexión persistente, secuencial",
                "cache": "sin caché de aplicación; MongoDB con caché WiredTiger por defecto",
            },
            "muestras": samples,
        }
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(json.dumps({k: v for k, v in result.items() if k != "muestras"}, indent=2, ensure_ascii=False))
    finally:
        for col in ("devices", "readings", "alerts", "events"):
            db[col].delete_many({"device_id": device_id})
        db.users.delete_one({"email": admin_email})


if __name__ == "__main__":
    main()
