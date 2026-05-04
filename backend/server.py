"""ColdChain Dashboard backend - FastAPI + MongoDB."""
from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import hmac
import hashlib
import io
import csv
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Response, Request
from fastapi.responses import StreamingResponse
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
    CreateUserRequest, UpdateUserRequest, AdminResetPasswordRequest,
    SelfChangePasswordRequest,
    DeviceApproveRequest, DeviceRejectRequest, TemperatureIngest,
    TransporterAccessRequest, ToggleHmacRequest, now_iso,
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

    if user.get("disabled"):
        raise HTTPException(status_code=403, detail="Usuario deshabilitado. Contacte al administrador.")

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


# ====== ADMIN: ALL USERS (admins + transporters) ======
def _public_user(u: dict) -> dict:
    return {
        "id": u.get("id"),
        "email": u.get("email"),
        "name": u.get("name"),
        "role": u.get("role"),
        "disabled": bool(u.get("disabled", False)),
        "must_change_password": bool(u.get("must_change_password", False)),
        "totp_enabled": bool(u.get("totp_enabled", False)),
        "created_at": u.get("created_at"),
    }


@api.get("/admin/users")
async def list_users(role: Optional[str] = None, admin=Depends(require_role("admin"))):
    q = {}
    if role in ("admin", "transporter"):
        q["role"] = role
    users = await db.users.find(q, {"_id": 0, "password_hash": 0, "totp_secret": 0}).to_list(1000)
    return [_public_user(u) for u in users]


@api.post("/admin/users")
async def create_user(body: CreateUserRequest, admin=Depends(require_role("admin"))):
    email = body.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Ya existe un usuario con ese correo")
    doc = {
        "id": str(uuid.uuid4()),
        "email": email,
        "name": body.name,
        "role": body.role,
        "password_hash": hash_password(body.password),
        "must_change_password": bool(body.must_change_password),
        "totp_enabled": False,
        "totp_secret": None,
        "disabled": False,
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    return _public_user(doc)


@api.patch("/admin/users/{user_id}")
async def update_user(user_id: str, body: UpdateUserRequest, admin=Depends(require_role("admin"))):
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    update: dict = {}
    if body.name is not None:
        update["name"] = body.name
    if body.role is not None:
        update["role"] = body.role
    if body.disabled is not None:
        # Cannot disable yourself
        if target["id"] == admin["id"] and body.disabled:
            raise HTTPException(status_code=400, detail="No puedes deshabilitar tu propia cuenta")
        update["disabled"] = bool(body.disabled)
    if body.must_change_password is not None:
        update["must_change_password"] = bool(body.must_change_password)
    if body.reset_2fa:
        update["totp_enabled"] = False
        update["totp_secret"] = None

    if update:
        await db.users.update_one({"id": user_id}, {"$set": update})
    refreshed = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0, "totp_secret": 0})
    return _public_user(refreshed)


@api.post("/admin/users/{user_id}/reset-password")
async def admin_reset_password(user_id: str, body: AdminResetPasswordRequest,
                               admin=Depends(require_role("admin"))):
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "password_hash": hash_password(body.new_password),
            "must_change_password": bool(body.must_change_password),
        }},
    )
    return {"ok": True}


@api.delete("/admin/users/{user_id}")
async def delete_user(user_id: str, admin=Depends(require_role("admin"))):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propia cuenta")
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    # Safety: prevent removing the last enabled admin
    if target.get("role") == "admin":
        remaining = await db.users.count_documents({"role": "admin", "disabled": {"$ne": True}, "id": {"$ne": user_id}})
        if remaining == 0:
            raise HTTPException(status_code=400, detail="No puedes eliminar el último administrador activo")
    await db.users.delete_one({"id": user_id})
    return {"ok": True}


# ====== SELF-SERVICE PASSWORD CHANGE ======
@api.post("/auth/change-my-password")
async def change_my_password(body: SelfChangePasswordRequest, user=Depends(get_current_user)):
    full = await db.users.find_one({"id": user["id"]})
    if not full or not verify_password(body.current_password, full["password_hash"]):
        raise HTTPException(status_code=401, detail="Contraseña actual incorrecta")
    if body.new_password == body.current_password:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe ser distinta a la actual")
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": hash_password(body.new_password),
                  "must_change_password": False}},
    )
    return {"ok": True}


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


@api.post("/devices/secure-mode")
async def toggle_secure_mode(body: ToggleHmacRequest, admin=Depends(require_role("admin"))):
    """Activar/desactivar modo seguro (HMAC obligatorio) por dispositivo."""
    res = await db.devices.update_one(
        {"device_id": body.device_id},
        {"$set": {"require_hmac": bool(body.require_hmac)}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    await db.events.insert_one({
        "id": str(uuid.uuid4()), "device_id": body.device_id,
        "type": "secure_mode_changed", "ts": now_iso(), "actor": admin["email"],
        "value": bool(body.require_hmac),
    })
    return {"ok": True, "require_hmac": bool(body.require_hmac)}


def _classify(t: float) -> str:
    if t < TEMP_MIN or t > TEMP_MAX:
        return "critical"
    if t <= WARN_LOW or t >= WARN_HIGH:
        return "warning"
    return "ok"


@api.get("/devices/{device_id}/export")
async def export_device(device_id: str, format: str = "csv", hours: int = 24,
                        admin=Depends(require_role("admin"))):
    """Exporta el histórico (CSV o PDF) del dispositivo en las últimas `hours` horas."""
    if format not in ("csv", "pdf"):
        raise HTTPException(status_code=400, detail="format debe ser csv o pdf")
    if hours <= 0 or hours > 24 * 365:
        raise HTTPException(status_code=400, detail="hours fuera de rango")

    device = await db.devices.find_one(
        {"device_id": device_id}, {"_id": 0, "device_password_hash": 0}
    )
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    readings = await db.readings.find(
        {"device_id": device_id, "ts": {"$gte": since}}, {"_id": 0}
    ).sort("ts", 1).to_list(100000)
    alerts = await db.alerts.find(
        {"device_id": device_id, "ts": {"$gte": since}}, {"_id": 0}
    ).sort("ts", 1).to_list(10000)

    fname_base = f"coldchain_{device_id}_{hours}h"

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["timestamp_iso", "device_id", "device_name",
                         "temperature_c", "status"])
        for r in readings:
            t = float(r["temperature"])
            writer.writerow([r["ts"], device_id, device.get("name", ""),
                             f"{t:.2f}", _classify(t)])
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{fname_base}.csv"'},
        )

    # ---- PDF ----
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, PageBreak)

    pdf_buf = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buf, pagesize=A4, leftMargin=18*mm,
                            rightMargin=18*mm, topMargin=18*mm, bottomMargin=18*mm)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], textColor=colors.HexColor("#0c4a6e"),
                        spaceAfter=4)
    label = ParagraphStyle("label", parent=styles["Normal"], textColor=colors.HexColor("#64748b"),
                           fontSize=8, leading=10, spaceAfter=0)
    body_st = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=14)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, leading=10,
                           textColor=colors.HexColor("#475569"))

    elements = []
    elements.append(Paragraph("ColdChain Dashboard — Reporte de cadena de frío", h1))
    elements.append(Paragraph(
        f"Dispositivo <b>{device_id}</b> · {device.get('name','')}<br/>"
        f"Periodo: últimas {hours} h · Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        small))
    elements.append(Spacer(1, 8))

    # Stats
    if readings:
        temps = [float(r["temperature"]) for r in readings]
        mn, mx = min(temps), max(temps)
        avg = sum(temps) / len(temps)
        out_of_range = sum(1 for t in temps if t < TEMP_MIN or t > TEMP_MAX)
        warn_count = sum(1 for t in temps
                         if (TEMP_MIN <= t <= TEMP_MAX) and (t <= WARN_LOW or t >= WARN_HIGH))
    else:
        mn = mx = avg = 0.0
        out_of_range = warn_count = 0

    stats_data = [
        ["Lecturas", "Mínima", "Máxima", "Promedio", "Críticas", "Preventivas"],
        [str(len(readings)), f"{mn:.2f} °C", f"{mx:.2f} °C", f"{avg:.2f} °C",
         str(out_of_range), str(warn_count)],
    ]
    t_stats = Table(stats_data, hAlign="LEFT", colWidths=[28*mm]*6)
    t_stats.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#f1f5f9")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
    ]))
    elements.append(t_stats)
    elements.append(Spacer(1, 14))

    # Alerts
    elements.append(Paragraph("Alertas del periodo", styles["Heading3"]))
    if alerts:
        a_rows = [["Severidad", "Temp.", "Mensaje", "Fecha/Hora (UTC)"]]
        for a in alerts:
            a_rows.append([
                a.get("severity", "").upper(),
                f"{float(a.get('temperature') or 0):.2f} °C",
                Paragraph(a.get("message", ""), small),
                a.get("ts", "")[:19].replace("T", " "),
            ])
        t_alerts = Table(a_rows, hAlign="LEFT", colWidths=[22*mm, 22*mm, 90*mm, 40*mm])
        t_alerts.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f8fafc")]),
        ]))
        elements.append(t_alerts)
    else:
        elements.append(Paragraph("Sin alertas en el periodo.", body_st))
    elements.append(Spacer(1, 14))

    # Readings (last 200 to keep PDF size manageable)
    elements.append(Paragraph("Últimas lecturas", styles["Heading3"]))
    rdg = readings[-200:]
    if rdg:
        r_rows = [["Fecha/Hora (UTC)", "Temp. (°C)", "Estado"]]
        for r in rdg:
            t_val = float(r["temperature"])
            r_rows.append([
                r["ts"][:19].replace("T", " "),
                f"{t_val:.2f}",
                _classify(t_val),
            ])
        t_rdg = Table(r_rows, hAlign="LEFT", colWidths=[55*mm, 35*mm, 40*mm])
        t_rdg.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f8fafc")]),
        ]))
        elements.append(t_rdg)
    else:
        elements.append(Paragraph("Sin lecturas en el periodo.", body_st))

    elements.append(Spacer(1, 12))
    elements.append(Paragraph(
        "Documento generado automáticamente. Rango objetivo 2°C – 8°C. "
        "Las alertas preventivas se emiten ≤2.5°C / ≥7.5°C; críticas <2°C / >8°C.",
        small))

    doc.build(elements)
    pdf_buf.seek(0)
    return StreamingResponse(
        pdf_buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname_base}.pdf"'},
    )


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
def _compute_hmac(secret: str, device_id: str, nonce: int, temperature: float) -> str:
    """HMAC-SHA256 hex of '{device_id}|{nonce}|{temperature}' with the device password as key.
    Temperature is normalised to 2 decimal places to avoid float-string mismatches.
    """
    msg = f"{device_id}|{nonce}|{temperature:.2f}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


@api.post("/temperatura")
async def ingest_temperature(body: TemperatureIngest):
    """Endpoint público al que el ESP32 hace POST. Auth por device_id + device_password.
    Soporta opcional HMAC + nonce anti-replay. Si el dispositivo tiene `require_hmac=True`,
    se exigen `nonce` y `signature` válidos.
    """
    device = await db.devices.find_one({"device_id": body.deviceId})
    if not device:
        # First time - register as pending. Si trae HMAC, lo validamos y lo dejamos
        # en modo seguro desde el inicio. Si no, queda en compatibilidad.
        require_hmac = False
        if body.nonce is not None and body.signature is not None:
            expected = _compute_hmac(body.devicePassword, body.deviceId, body.nonce, body.temperature)
            if not hmac.compare_digest(expected, body.signature):
                raise HTTPException(status_code=401, detail="Firma HMAC inválida")
            require_hmac = True
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
            "require_hmac": require_hmac,
            "last_nonce": body.nonce if body.nonce is not None else 0,
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

    # HMAC validation
    require_hmac = bool(device.get("require_hmac", False))
    if require_hmac or body.signature is not None:
        if body.nonce is None or body.signature is None:
            raise HTTPException(status_code=401, detail="Falta nonce/signature (modo seguro activo)")
        expected = _compute_hmac(body.devicePassword, body.deviceId, body.nonce, body.temperature)
        if not hmac.compare_digest(expected, body.signature):
            raise HTTPException(status_code=401, detail="Firma HMAC inválida")
        last_nonce = int(device.get("last_nonce") or 0)
        if body.nonce <= last_nonce:
            raise HTTPException(status_code=409, detail="Nonce reutilizado (replay)")

    if device["status"] == "rejected":
        raise HTTPException(status_code=403, detail="Dispositivo rechazado")
    if device["status"] == "pending":
        # update last_seen but don't accept readings
        upd = {"last_seen": now_iso()}
        if body.nonce is not None:
            upd["last_nonce"] = body.nonce
        await db.devices.update_one({"device_id": body.deviceId}, {"$set": upd})
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
        {"$set": {
            "last_seen": ts,
            "last_temperature": body.temperature,
            **({"last_nonce": body.nonce} if body.nonce is not None else {}),
        }},
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
