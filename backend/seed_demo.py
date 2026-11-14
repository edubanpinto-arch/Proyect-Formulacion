"""Seed idempotente de datos de demostración (dispositivos y lecturas) y reinicio de datos de prueba.

    python seed_demo.py           # crea/restaura DEMO_ESP32_01 y DEMO_ESP32_02 aprobados con 24 lecturas cada uno
    python seed_demo.py --reset   # además borra todos los datos de prueba con prefijo TEST_
Ejecutarlo varias veces deja siempre el mismo estado (mismos IDs y lecturas).
"""
import os
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

import bcrypt
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).parent / ".env")

DEMO = [
    {"device_id": "DEMO_ESP32_01", "name": "Nevera demo 01", "password": "Demo_Clave_01", "base": 5.0},
    {"device_id": "DEMO_ESP32_02", "name": "Nevera demo 02", "password": "Demo_Clave_02", "base": 4.2},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    if args.reset:
        rx = {"$regex": "^TEST_"}
        for col in ("devices", "readings", "alerts", "events"):
            n = db[col].delete_many({"device_id": rx}).deleted_count
            print(f"reset {col}: {n} documentos TEST_ eliminados")

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for d in DEMO:
        existing = db.devices.find_one({"device_id": d["device_id"]})
        pwd_hash = existing["device_password_hash"] if existing and bcrypt.checkpw(
            d["password"].encode(), existing["device_password_hash"].encode()) else \
            bcrypt.hashpw(d["password"].encode(), bcrypt.gensalt()).decode()
        readings = [{"id": f"{d['device_id']}_R{i:02d}", "device_id": d["device_id"],
                     "temperature": round(d["base"] + ((i % 6) - 2.5) * 0.3, 2),
                     "ts": (now - timedelta(hours=23 - i)).isoformat()} for i in range(24)]
        db.devices.update_one({"device_id": d["device_id"]}, {"$set": {
            "id": d["device_id"], "device_id": d["device_id"], "name": d["name"],
            "device_password_hash": pwd_hash, "status": "approved", "created_at": readings[0]["ts"],
            "approved_at": readings[0]["ts"], "approved_by": "seed_demo", "last_seen": readings[-1]["ts"],
            "last_temperature": readings[-1]["temperature"], "transporter_email": None,
            "require_hmac": False, "last_nonce": 0,
        }}, upsert=True)
        db.readings.delete_many({"device_id": d["device_id"]})
        db.readings.insert_many(readings)
        db.alerts.delete_many({"device_id": d["device_id"]})
        print(f"{d['device_id']}: aprobado, {len(readings)} lecturas (clave {d['password']})")


if __name__ == "__main__":
    main()
