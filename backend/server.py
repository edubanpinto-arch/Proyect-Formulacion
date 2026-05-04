"""ColdChain Dashboard backend - FastAPI + MongoDB."""
from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Response, Request
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

import auth as auth_mod
from auth import (
    hash_password, verify_password, create_access_token, create_temp_token,
    decode_token, totp_verify, totp_provisioning_uri, generate_totp_secret,
    make_qr_data_url, get_current_user, require_role, set_auth_cookie, clear_auth_cookie,
)
from models import (
    LoginRequest, TwoFactorVerifyRequest, TwoFactorEnrollVerifyRequest,
    ChangePasswordRequest, CreateTransporterRequest,
    DeviceApproveRequest, DeviceRejectRequest, TemperatureIngest,
    TransporterAccessRequest, now_iso,
)

logger = logging.getLogger("coldchain")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="ColdChain Dashboard")
api = APIRouter(prefix="/api")

# --- Constants ---
TEMP_MIN = 2.0
TEMP_MAX = 8.0
WARN_LOW = 2.5
WARN_HIGH = 7.5
INACTIVE_AFTER_SECONDS = 60  # device considered inactive if no reading for 60s


# ====== AUTH ======
@api.post("/auth/login")
async def login(body: LoginRequest, response: Response):
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    # First step: must change password
    if user.get("must_change_password"):
        token = create_temp_token(user["id"], user["email"], "must_change_password")
        return {"step": "change_password", "temp_token": token}

    # Admin: 2FA flow
    if user.get("role") == "admin":
        if not user.get("totp_enabled"):
            # Force enrollment - create secret if not exists
            if not user.get("totp_secret"):
                secret = generate_totp_secret()
                await db.users.update_one({"id": user["id"]}, {"$set": {"totp_secret": secret}})
            else:
                secret = user["totp_secret"]
            token = create_temp_token(user["id"], user["email"], "enroll_2fa")
            uri = totp_provisioning_uri(secret, user["email"])
            return {
                "step": "enroll_2fa",
                "temp_token": token,
                "secret": secret,
                "qr_data_url": make_qr_data_url(uri),
            }
        token = create_temp_token(user["id"], user["email"], "verify_2fa")
        return {"step": "verify_2fa", "temp_token": token}

    # Transportador: direct login
    access = create_access_token(user["id"], user["email"], user["role"], mfa_passed=True)
    set_auth_cookie(response, access)
    return {
        "step": "ok",
        "access_token": access,
        "user": {
            "id": user["id"], "email": user["email"], "name": user["name"],
            "role": user["role"], "must_change_password": False, "totp_enabled": False,
        },
    }


@api.post("/auth/change-password")
async def change_password(body: ChangePasswordRequest, response: Response):
    """Used both for forced first-time change (with temp_token) and self-service."""
    if body.temp_token:
        try:
            payload = decode_token(body.temp_token)
        except Exception:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")
        if payload.get("purpose") != "must_change_password":
            raise HTTPException(status_code=401, detail="Token inválido")
        user = await db.users.find_one({"id": payload["sub"]})
    else:
        # Self-service requires Authorization
        raise HTTPException(status_code=400, detail="temp_token requerido")

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres")

    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": hash_password(body.new_password), "must_change_password": False}},
    )

    # Re-issue login flow: admins now go to enroll_2fa
    if user["role"] == "admin":
        if not user.get("totp_secret"):
            secret = generate_totp_secret()
            await db.users.update_one({"id": user["id"]}, {"$set": {"totp_secret": secret}})
        else:
            secret = user["totp_secret"]
        token = create_temp_token(user["id"], user["email"], "enroll_2fa")
        uri = totp_provisioning_uri(secret, user["email"])
        return {
            "step": "enroll_2fa",
            "temp_token": token,
            "secret": secret,
            "qr_data_url": make_qr_data_url(uri),
        }

    access = create_access_token(user["id"], user["email"], user["role"], True)
    set_auth_cookie(response, access)
    return {"step": "ok", "access_token": access}


@api.post("/auth/2fa/enroll-verify")
async def enroll_2fa(body: TwoFactorEnrollVerifyRequest, response: Response):
    try:
        payload = decode_token(body.temp_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    if payload.get("purpose") != "enroll_2fa":
        raise HTTPException(status_code=401, detail="Token inválido")

    user = await db.users.find_one({"id": payload["sub"]})
    if not user or not user.get("totp_secret"):
        raise HTTPException(status_code=400, detail="No hay secreto TOTP")
    if not totp_verify(user["totp_secret"], body.code):
        raise HTTPException(status_code=401, detail="Código TOTP incorrecto")

    await db.users.update_one({"id": user["id"]}, {"$set": {"totp_enabled": True}})
    access = create_access_token(user["id"], user["email"], user["role"], True)
    set_auth_cookie(response, access)
    return {"step": "ok", "access_token": access}


@api.post("/auth/2fa/verify")
async def verify_2fa(body: TwoFactorVerifyRequest, response: Response):
    try:
        payload = decode_token(body.temp_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    if payload.get("purpose") != "verify_2fa":
        raise HTTPException(status_code=401, detail="Token inválido")
    user = await db.users.find_one({"id": payload["sub"]})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not totp_verify(user.get("totp_secret", ""), body.code):
        raise HTTPException(status_code=401, detail="Código TOTP incorrecto")
    access = create_access_token(user["id"], user["email"], user["role"], True)
    set_auth_cookie(response, access)
    return {"step": "ok", "access_token": access}


@api.get("/auth/me")
async def auth_me(user=Depends(get_current_user)):
    return user


@api.post("/auth/logout")
async def logout(response: Response):
    clear_auth_cookie(response)
    return {"ok": True}


# ====== ADMIN: USERS / TRANSPORTERS ======
@api.post("/admin/transporters")
async def create_transporter(body: CreateTransporterRequest, admin=Depends(require_role("admin"))):
    email = body.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Ya existe un usuario con ese correo")
    user_doc = {
        "id": str(uuid.uuid4()),
        "email": email,
        "name": body.name,
        "role": "transporter",
        "password_hash": hash_password(body.password),
        "must_change_password": False,
        "totp_enabled": False,
        "created_at": now_iso(),
    }
    await db.users.insert_one(user_doc)
    return {"id": user_doc["id"], "email": email, "name": body.name, "role": "transporter"}


@api.get("/admin/transporters")
async def list_transporters(admin=Depends(require_role("admin"))):
    items = await db.users.find(
        {"role": "transporter"},
        {"_id": 0, "password_hash": 0, "totp_secret": 0},
    ).to_list(500)
    return items


# ====== DEVICES ======
async def _device_status(device: dict) -> str:
    if device.get("status") == "pending":
        return "pending"
    if device.get("status") == "rejected":
        return "rejected"
    last = device.get("last_seen")
    if not last:
        return "inactive"
    last_dt = datetime.fromisoformat(last)
    if datetime.now(timezone.utc) - last_dt > timedelta(seconds=INACTIVE_AFTER_SECONDS):
        return "inactive"
    return "active"


@api.get("/devices")
async def list_devices(admin=Depends(require_role("admin"))):
    devices = await db.devices.find({}, {"_id": 0, "device_password_hash": 0}).to_list(1000)
    out = []
    for d in devices:
        d["live_status"] = await _device_status(d)
        out.append(d)
    return out


@api.get("/devices/pending")
async def pending_devices(admin=Depends(require_role("admin"))):
    return await db.devices.find(
        {"status": "pending"}, {"_id": 0, "device_password_hash": 0}
    ).to_list(500)


@api.post("/devices/approve")
async def approve_device(body: DeviceApproveRequest, admin=Depends(require_role("admin"))):
    device = await db.devices.find_one({"device_id": body.device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    update = {"status": "approved", "approved_at": now_iso(), "approved_by": admin["email"]}
    if body.name:
        update["name"] = body.name
    if body.transporter_email:
        update["transporter_email"] = body.transporter_email.lower().strip()
    await db.devices.update_one({"device_id": body.device_id}, {"$set": update})
    await db.events.insert_one({
        "id": str(uuid.uuid4()), "device_id": body.device_id,
        "type": "device_approved", "ts": now_iso(), "actor": admin["email"],
    })
    return {"ok": True}


@api.post("/devices/reject")
async def reject_device(body: DeviceRejectRequest, admin=Depends(require_role("admin"))):
    await db.devices.update_one(
        {"device_id": body.device_id},
        {"$set": {"status": "rejected", "rejected_at": now_iso()}},
    )
    return {"ok": True}


@api.get("/devices/{device_id}")
async def device_detail(device_id: str, admin=Depends(require_role("admin"))):
    d = await db.devices.find_one({"device_id": device_id}, {"_id": 0, "device_password_hash": 0})
    if not d:
        raise HTTPException(status_code=404, detail="No encontrado")
    d["live_status"] = await _device_status(d)
    return d


@api.get("/devices/{device_id}/readings")
async def device_readings(device_id: str, limit: int = 200, admin=Depends(require_role("admin"))):
    items = await db.readings.find(
        {"device_id": device_id}, {"_id": 0}
    ).sort("ts", -1).to_list(limit)
    items.reverse()
    return items


@api.get("/devices/{device_id}/alerts")
async def device_alerts(device_id: str, admin=Depends(require_role("admin"))):
    return await db.alerts.find(
        {"device_id": device_id}, {"_id": 0}
    ).sort("ts", -1).to_list(200)


# ====== ALERTS ======
@api.get("/alerts")
async def list_alerts(active_only: bool = False, admin=Depends(require_role("admin"))):
    q = {"acknowledged": False} if active_only else {}
    return await db.alerts.find(q, {"_id": 0}).sort("ts", -1).to_list(500)


@api.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: str, admin=Depends(require_role("admin"))):
    await db.alerts.update_one(
        {"id": alert_id},
        {"$set": {"acknowledged": True, "acknowledged_by": admin["email"], "acknowledged_at": now_iso()}},
    )
    return {"ok": True}


# ====== STATS ======
@api.get("/stats/summary")
async def stats_summary(admin=Depends(require_role("admin"))):
    devices = await db.devices.find({}).to_list(1000)
    active = inactive = pending = 0
    for d in devices:
        st = await _device_status(d)
        if st == "active":
            active += 1
        elif st == "inactive":
            inactive += 1
        elif st == "pending":
            pending += 1
    critical = await db.alerts.count_documents({"acknowledged": False, "severity": "critical"})
    warning = await db.alerts.count_documents({"acknowledged": False, "severity": "warning"})
    return {
        "active": active, "inactive": inactive, "pending": pending,
        "critical_alerts": critical, "warning_alerts": warning,
        "total_devices": len(devices),
    }


# ====== TEMPERATURE INGEST (ESP32) ======
@api.post("/temperatura")
async def ingest_temperature(body: TemperatureIngest):
    """Endpoint público al que el ESP32 hace POST. Auth por device_id + device_password."""
    device = await db.devices.find_one({"device_id": body.deviceId})
    if not device:
        # First time - register as pending and store password hash
        new_dev = {
            "id": str(uuid.uuid4()),
            "device_id": body.deviceId,
            "name": body.deviceId,
            "device_password_hash": hash_password(body.devicePassword),
            "status": "pending",
            "created_at": now_iso(),
            "last_seen": now_iso(),
            "last_temperature": body.temperature,
            "transporter_email": None,
        }
        await db.devices.insert_one(new_dev)
        await db.events.insert_one({
            "id": str(uuid.uuid4()), "device_id": body.deviceId,
            "type": "device_registered_pending", "ts": now_iso(),
        })
        return {"ok": True, "status": "pending", "message": "Dispositivo registrado, esperando aprobación"}

    # verify password
    if not verify_password(body.devicePassword, device.get("device_password_hash", "")):
        raise HTTPException(status_code=401, detail="Contraseña del dispositivo inválida")

    if device["status"] == "rejected":
        raise HTTPException(status_code=403, detail="Dispositivo rechazado")
    if device["status"] == "pending":
        # update last_seen but don't accept readings
        await db.devices.update_one(
            {"device_id": body.deviceId},
            {"$set": {"last_seen": now_iso()}},
        )
        return {"ok": True, "status": "pending", "message": "Esperando aprobación del administrador"}

    # store reading
    reading_id = str(uuid.uuid4())
    ts = now_iso()
    await db.readings.insert_one({
        "id": reading_id, "device_id": body.deviceId,
        "temperature": body.temperature, "ts": ts,
    })
    await db.devices.update_one(
        {"device_id": body.deviceId},
        {"$set": {"last_seen": ts, "last_temperature": body.temperature}},
    )

    # Alerting logic
    sev = None
    msg = None
    t = body.temperature
    if t < TEMP_MIN or t > TEMP_MAX:
        sev = "critical"
        msg = (
            f"TEMPERATURA FUERA DE RANGO ({t:.2f}°C). Cadena de frío comprometida."
            if (t > TEMP_MAX) else
            f"TEMPERATURA CRÍTICA BAJA ({t:.2f}°C). Cadena de frío comprometida."
        )
    elif t <= WARN_LOW or t >= WARN_HIGH:
        sev = "warning"
        msg = f"Temperatura cercana al límite ({t:.2f}°C). Acción preventiva."

    if sev:
        await db.alerts.insert_one({
            "id": str(uuid.uuid4()),
            "device_id": body.deviceId,
            "device_name": device.get("name", body.deviceId),
            "severity": sev,
            "type": "temperature_out_of_range" if sev == "critical" else "temperature_warning",
            "message": msg,
            "temperature": t,
            "ts": ts,
            "acknowledged": False,
        })

    return {"ok": True, "status": "active", "alert": sev}


# ====== TRANSPORTER VIEW ======
@api.post("/transporter/access")
async def transporter_access(body: TransporterAccessRequest, user=Depends(require_role("transporter"))):
    """A transporter unlocks a device by entering its hardware password.
    We find a device whose password matches AND is assigned to this transporter (or any approved if not yet assigned)."""
    candidates = await db.devices.find({"status": "approved"}).to_list(500)
    matched = None
    for d in candidates:
        if verify_password(body.device_password, d.get("device_password_hash", "")):
            # if device has assigned transporter, must match
            if d.get("transporter_email") and d["transporter_email"] != user["email"]:
                continue
            matched = d
            break
    if not matched:
        raise HTTPException(status_code=401, detail="Contraseña del hardware incorrecta o no autorizada")

    # auto-assign on first access
    if not matched.get("transporter_email"):
        await db.devices.update_one(
            {"device_id": matched["device_id"]},
            {"$set": {"transporter_email": user["email"]}},
        )
        matched["transporter_email"] = user["email"]

    # Issue a per-session "device unlock" token in cookie? For simplicity, return device_id and rely on it
    matched["live_status"] = await _device_status(matched)
    matched.pop("device_password_hash", None)
    matched.pop("_id", None)
    return matched


@api.get("/transporter/device/{device_id}")
async def transporter_device(device_id: str, user=Depends(require_role("transporter"))):
    d = await db.devices.find_one({"device_id": device_id}, {"_id": 0, "device_password_hash": 0})
    if not d or d.get("status") != "approved":
        raise HTTPException(status_code=404, detail="No encontrado")
    if d.get("transporter_email") != user["email"]:
        raise HTTPException(status_code=403, detail="No autorizado")
    d["live_status"] = await _device_status(d)
    readings = await db.readings.find({"device_id": device_id}, {"_id": 0}).sort("ts", -1).to_list(60)
    readings.reverse()
    alerts = await db.alerts.find({"device_id": device_id}, {"_id": 0}).sort("ts", -1).to_list(20)
    return {"device": d, "readings": readings, "alerts": alerts}


# ====== SEEDING / STARTUP ======
async def seed_admin():
    email = os.environ["ADMIN_EMAIL"].lower().strip()
    password = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": email})
    if not existing:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": email,
            "name": "Administrador",
            "role": "admin",
            "password_hash": hash_password(password),
            "must_change_password": True,
            "totp_enabled": False,
            "totp_secret": None,
            "created_at": now_iso(),
        })
        logger.info(f"Admin seeded: {email}")
    else:
        logger.info(f"Admin already present: {email}")

    # Seed a default transporter for testing
    t_email = "transportador@coldchain.com"
    if not await db.users.find_one({"email": t_email}):
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": t_email,
            "name": "Transportador Demo",
            "role": "transporter",
            "password_hash": hash_password("transport123"),
            "must_change_password": False,
            "totp_enabled": False,
            "created_at": now_iso(),
        })
        logger.info(f"Transporter seeded: {t_email}")


async def ensure_indexes():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.devices.create_index("device_id", unique=True)
    await db.readings.create_index([("device_id", 1), ("ts", -1)])
    await db.alerts.create_index([("device_id", 1), ("ts", -1)])


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()
    await seed_admin()


@app.on_event("shutdown")
async def on_shutdown():
    client.close()


# ----- mount -----
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_origin_regex=".*",
    allow_methods=["*"],
    allow_headers=["*"],
)
