"""Setup/cleanup helper for iteration-4 UI tests. Usage: python ui_setup_iter4.py setup|cleanup"""
import os, sys, requests, pyotp
from pymongo import MongoClient
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
DEVS = [("TEST_UI_A", "UIPWA_111"), ("TEST_UI_B", "UIPWB_222")]


def admin():
    d = requests.post(f"{API}/auth/login", json={"email": "qa_admin@coldchain.com", "password": "QaAdmin123!"}).json()
    r = requests.post(f"{API}/auth/2fa/verify", json={"temp_token": d["temp_token"], "code": pyotp.TOTP("FJ7WS2VVIJ5YMZO4JPIQFG2UV75DZPR6").now()})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


if sys.argv[1] == "setup":
    h = admin()
    for dev, pw in DEVS:
        print(requests.post(f"{API}/temperatura", json={"deviceId": dev, "devicePassword": pw, "temperature": 5.0}).json())
        print(requests.post(f"{API}/devices/approve", headers=h, json={"device_id": dev, "transporter_email": "transportador@coldchain.com"}).json())
    for t in (9.5, 10.0, 1.0, 7.8):
        print(requests.post(f"{API}/temperatura", json={"deviceId": "TEST_UI_A", "devicePassword": "UIPWA_111", "temperature": t}).json())
    print(requests.post(f"{API}/temperatura", json={"deviceId": "TEST_UI_B", "devicePassword": "UIPWB_222", "temperature": 9.0}).json())
    tr = requests.get(f"{API}/transporter/devices", headers={"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "transportador@coldchain.com", "password": "transport123"}).json()["access_token"]}).json()
    print("assigned_total", tr["assigned_total"])
else:
    db = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))["coldchain_db"]
    for dev, _ in DEVS:
        for c in ("devices",):
            db[c].delete_one({"device_id": dev})
        for c in ("readings", "alerts", "events"):
            db[c].delete_many({"device_id": dev})
    print("cleaned")
