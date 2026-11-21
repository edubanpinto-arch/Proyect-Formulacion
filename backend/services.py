"""Servicios de aplicación: reglas de negocio de RF-01 (ingesta) y RF-02 (alertas).
No dependen de HTTP; comunican resultados con excepciones de dominio."""
import hmac
import uuid
import asyncio
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional

from auth import hash_password, verify_password
from models import now_iso
from repositories import DeviceRepository, ReadingRepository, AlertRepository, EventRepository, DuplicateDevice

TEMP_MIN = 2.0
TEMP_MAX = 8.0
WARN_LOW = 2.5
WARN_HIGH = 7.5
INACTIVE_AFTER_SECONDS = 60


class DomainError(Exception):
    status = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class InvalidCredentials(DomainError):
    status = 401


class Forbidden(DomainError):
    status = 403


class NotFound(DomainError):
    status = 404


class Conflict(DomainError):
    status = 409


def classify_temperature(t: float) -> Optional[str]:
    """Regla RF-02: <2 o >8 °C crítica; [2, 2.5] o [7.5, 8] preventiva; resto sin alerta."""
    if t < TEMP_MIN or t > TEMP_MAX:
        return "critical"
    if t <= WARN_LOW or t >= WARN_HIGH:
        return "warning"
    return None


def alert_message(t: float, severity: str) -> str:
    if severity == "critical":
        if t > TEMP_MAX:
            return f"TEMPERATURA FUERA DE RANGO ({t:.2f}°C). Cadena de frío comprometida."
        return f"TEMPERATURA CRÍTICA BAJA ({t:.2f}°C). Cadena de frío comprometida."
    return f"Temperatura cercana al límite ({t:.2f}°C). Acción preventiva."


def compute_hmac(secret: str, device_id: str, nonce: int, temperature: float) -> str:
    msg = f"{device_id}|{nonce}|{temperature:.2f}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def device_live_status(device: dict, now: Optional[datetime] = None) -> str:
    if device.get("status") in ("pending", "rejected"):
        return device["status"]
    last = device.get("last_seen")
    if not last:
        return "inactive"
    now = now or datetime.now(timezone.utc)
    if now - datetime.fromisoformat(last) > timedelta(seconds=INACTIVE_AFTER_SECONDS):
        return "inactive"
    return "active"


class AlertService:
    """RF-02: evaluar lecturas, listar y reconocer alertas."""

    def __init__(self, alerts: AlertRepository, devices: DeviceRepository):
        self.alerts = alerts
        self.devices = devices

    async def evaluate(self, device: dict, temperature: float, ts: str) -> Optional[dict]:
        severity = classify_temperature(temperature)
        if not severity:
            return None
        alert = {
            "id": str(uuid.uuid4()),
            "device_id": device["device_id"],
            "device_name": device.get("name", device["device_id"]),
            "severity": severity,
            "type": "temperature_out_of_range" if severity == "critical" else "temperature_warning",
            "message": alert_message(temperature, severity),
            "temperature": temperature,
            "ts": ts,
            "acknowledged": False,
        }
        await self.alerts.insert(alert)
        return alert

    async def list_alerts(self, active_only: bool) -> list:
        return await self.alerts.list(active_only)

    async def list_device_alerts(self, device_id: str) -> list:
        if not await self.devices.exists(device_id):
            raise NotFound("El dispositivo no existe.")
        return await self.alerts.list_by_device(device_id)

    async def acknowledge(self, alert_id: str, actor_email: str) -> dict:
        alert = await self.alerts.find_by_id(alert_id)
        if not alert:
            raise NotFound("La alerta no existe.")
        if alert.get("acknowledged"):
            return alert
        ts = now_iso()
        await self.alerts.acknowledge(alert_id, actor_email, ts)
        return {**alert, "acknowledged": True, "acknowledged_by": actor_email, "acknowledged_at": ts}

    async def acknowledge_device(self, device_id: str, actor_email: str) -> int:
        if not await self.devices.exists(device_id):
            raise NotFound("El dispositivo no existe.")
        return await self.alerts.acknowledge_all_for_device(device_id, actor_email, now_iso())


class IngestionService:
    """RF-01: recibir una lectura del ESP32, validar el dispositivo y persistirla solo si está aprobado."""

    def __init__(self, devices: DeviceRepository, readings: ReadingRepository,
                 events: EventRepository, alert_service: AlertService):
        self.devices = devices
        self.readings = readings
        self.events = events
        self.alert_service = alert_service

    @staticmethod
    def _signature_ok(password: str, device_id: str, nonce: int, temperature: float, signature: str) -> bool:
        return hmac.compare_digest(compute_hmac(password, device_id, nonce, temperature), signature)

    async def _register_pending(self, device_id: str, password: str, temperature: float,
                                nonce: Optional[int], signature: Optional[str]) -> dict:
        require_hmac = nonce is not None and signature is not None
        if require_hmac and not self._signature_ok(password, device_id, nonce, temperature, signature):
            raise InvalidCredentials("Firma HMAC inválida")
        ts = now_iso()
        try:
            await self.devices.insert({
                "id": str(uuid.uuid4()), "device_id": device_id, "name": device_id,
                "device_password_hash": await asyncio.to_thread(hash_password, password),
                "device_password_plain": password,          # guardado para que admin pueda compartirlo
                "status": "pending", "created_at": ts, "last_seen": ts,
                "last_temperature": temperature, "transporter_email": None,
                "require_hmac": require_hmac, "last_nonce": nonce if nonce is not None else 0,
            })
        except DuplicateDevice:
            raise Conflict("El dispositivo ya está registrado; reintente el envío.")
        await self.events.insert({"id": str(uuid.uuid4()), "device_id": device_id,
                                  "type": "device_registered_pending", "ts": ts})
        return {"ok": True, "status": "pending", "message": "Dispositivo registrado, esperando aprobación"}

    async def ingest(self, device_id: str, password: str, temperature: float,
                     nonce: Optional[int] = None, signature: Optional[str] = None) -> dict:
        device = await self.devices.find_by_device_id(device_id)
        if not device:
            return await self._register_pending(device_id, password, temperature, nonce, signature)

        if not await asyncio.to_thread(verify_password, password, device.get("device_password_hash", "")):
            raise InvalidCredentials("Contraseña del dispositivo inválida")

        if device.get("require_hmac") or signature is not None:
            if nonce is None or signature is None:
                raise InvalidCredentials("Falta nonce/signature (modo seguro activo)")
            if not self._signature_ok(password, device_id, nonce, temperature, signature):
                raise InvalidCredentials("Firma HMAC inválida")
            stored_nonce = int(device.get("last_nonce") or 0)
            EPOCH_THRESHOLD = 1_000_000_000  # ~año 2001: distingue epoch-Unix de millis-uptime
            # Permitir si el nuevo nonce es epoch-scale y el guardado era millis-scale
            # (dispositivo reiniciado y actualizado a firmware NTP)
            epoch_upgrade = (nonce >= EPOCH_THRESHOLD and stored_nonce < EPOCH_THRESHOLD)
            if nonce <= stored_nonce and not epoch_upgrade:
                raise Conflict("Nonce reutilizado (replay)")

        nonce_upd = {"last_nonce": nonce} if nonce is not None else {}
        if device["status"] == "rejected":
            raise Forbidden("Dispositivo rechazado")
        if device["status"] == "pending":
            await self.devices.update_fields(device_id, {"last_seen": now_iso(), **nonce_upd})
            return {"ok": True, "status": "pending", "message": "Esperando aprobación del administrador"}

        ts = now_iso()
        reading_id = str(uuid.uuid4())
        await self.readings.insert({"id": reading_id, "device_id": device_id,
                                    "temperature": temperature, "ts": ts})
        await self.devices.update_fields(device_id, {"last_seen": ts, "last_temperature": temperature, **nonce_upd})
        alert = await self.alert_service.evaluate(device, temperature, ts)
        return {"ok": True, "status": "active", "reading_id": reading_id,
                "alert": alert["severity"] if alert else None}
