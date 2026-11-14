"""RNF-04 – Recuperabilidad: las lecturas confirmadas con 200 siguen consultables tras reiniciar backend y MongoDB.

Fase 1 (antes del reinicio): envía N lecturas a un dispositivo aprobado y guarda los reading_id confirmados.
    python tests/rnf04_reinicio.py antes --base-url http://localhost:8001 --n 20 --state ../documentacion/evidencias/rnf04_estado.json
Reiniciar backend y MongoDB (p. ej. Ctrl+C a uvicorn y `net stop MongoDB && net start MongoDB` en Windows).
Fase 2 (después del reinicio): consulta por la API cada reading_id confirmado.
    python tests/rnf04_reinicio.py despues --base-url http://localhost:8001 --state ../documentacion/evidencias/rnf04_estado.json --out ../documentacion/evidencias/rnf04_reinicio.json
"""
import os
import json
import uuid
import argparse
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
import pyotp
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def admin_session(api, db, email, pwd, secret):
    if not db.users.find_one({"email": email}):
        db.users.insert_one({"id": str(uuid.uuid4()), "email": email, "name": "QA RNF04", "role": "admin",
                             "password_hash": bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
                             "must_change_password": False, "totp_enabled": True, "totp_secret": secret,
                             "created_at": datetime.now(timezone.utc).isoformat()})
    tmp = requests.post(f"{api}/auth/login", json={"email": email, "password": pwd}).json()["temp_token"]
    tok = requests.post(f"{api}/auth/2fa/verify", json={"temp_token": tmp, "code": pyotp.TOTP(secret).now()}).json()
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok['access_token']}"
    return s


def antes(args, api, db):
    st = {"email": f"qa_rnf04_{uuid.uuid4().hex[:6]}@coldchain.com", "pwd": "QaRnf04!",
          "secret": pyotp.random_base32(), "device_id": f"TEST_RNF04_{uuid.uuid4().hex[:6]}",
          "device_pwd": "Clave_RNF04"}
    admin = admin_session(api, db, st["email"], st["pwd"], st["secret"])
    body = {"deviceId": st["device_id"], "devicePassword": st["device_pwd"], "temperature": 5.0}
    requests.post(f"{api}/temperatura", json=body)
    admin.post(f"{api}/devices/approve", json={"device_id": st["device_id"]})
    confirmed = []
    for i in range(args.n):
        r = requests.post(f"{api}/temperatura", json={**body, "temperature": 4.0 + i / 10})
        if r.status_code == 200 and r.json().get("reading_id"):
            confirmed.append(r.json()["reading_id"])
    st["confirmed"] = confirmed
    st["count_before"] = db.readings.count_documents({"device_id": st["device_id"]})
    st["ts_before"] = datetime.now(timezone.utc).isoformat()
    Path(args.state).parent.mkdir(parents=True, exist_ok=True)
    Path(args.state).write_text(json.dumps(st, indent=2))
    print(f"Confirmadas con 200: {len(confirmed)}  | readings en BD: {st['count_before']}")
    print("Ahora reinicie backend y MongoDB y ejecute la fase 'despues'.")


def despues(args, api, db):
    st = json.loads(Path(args.state).read_text())
    admin = admin_session(api, db, st["email"], st["pwd"], st["secret"])
    r = admin.get(f"{api}/devices/{st['device_id']}/readings", params={"limit": 1000})
    api_ids = {x["id"] for x in r.json()}
    found = [rid for rid in st["confirmed"] if rid in api_ids]
    result = {
        "rnf": "RNF-04", "device_id": st["device_id"], "confirmadas_200": len(st["confirmed"]),
        "consultables_tras_reinicio": len(found),
        "porcentaje": round(100 * len(found) / max(1, len(st["confirmed"])), 2),
        "count_antes": st["count_before"],
        "count_despues": db.readings.count_documents({"device_id": st["device_id"]}),
        "ts_antes": st["ts_before"], "ts_despues": datetime.now(timezone.utc).isoformat(),
        "reinicio": args.restart_note,
    }
    result["cumple"] = result["porcentaje"] == 100.0
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    for col in ("devices", "readings", "alerts", "events"):
        db[col].delete_many({"device_id": st["device_id"]})
    db.users.delete_one({"email": st["email"]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fase", choices=["antes", "despues"])
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--state", required=True)
    ap.add_argument("--out")
    ap.add_argument("--restart-note", default="backend y MongoDB reiniciados manualmente")
    args = ap.parse_args()
    api = args.base_url.rstrip("/") + "/api"
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    (antes if args.fase == "antes" else despues)(args, api, db)


if __name__ == "__main__":
    main()
