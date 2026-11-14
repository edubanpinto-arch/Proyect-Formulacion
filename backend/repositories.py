"""Capa de persistencia (repositorios) para RF-01 (ingesta) y RF-02 (alertas)."""
from typing import Optional
from pymongo.errors import DuplicateKeyError

NO_ID = {"_id": 0}


class DuplicateDevice(Exception):
    pass


class DeviceRepository:
    def __init__(self, db):
        self.col = db.devices

    async def find_by_device_id(self, device_id: str) -> Optional[dict]:
        return await self.col.find_one({"device_id": device_id}, NO_ID)

    async def insert(self, device: dict) -> None:
        try:
            await self.col.insert_one(dict(device))
        except DuplicateKeyError as e:
            raise DuplicateDevice(device["device_id"]) from e

    async def update_fields(self, device_id: str, fields: dict) -> None:
        await self.col.update_one({"device_id": device_id}, {"$set": fields})

    async def exists(self, device_id: str) -> bool:
        return await self.col.count_documents({"device_id": device_id}, limit=1) > 0


class ReadingRepository:
    def __init__(self, db):
        self.col = db.readings

    async def insert(self, reading: dict) -> None:
        await self.col.insert_one(dict(reading))

    async def list_by_device(self, device_id: str, limit: int) -> list:
        return await self.col.find({"device_id": device_id}, NO_ID).sort("ts", -1).to_list(limit)


class AlertRepository:
    def __init__(self, db):
        self.col = db.alerts

    async def insert(self, alert: dict) -> None:
        await self.col.insert_one(dict(alert))

    async def list(self, active_only: bool, limit: int = 500) -> list:
        q = {"acknowledged": False} if active_only else {}
        return await self.col.find(q, NO_ID).sort("ts", -1).to_list(limit)

    async def list_by_device(self, device_id: str, limit: int = 200) -> list:
        return await self.col.find({"device_id": device_id}, NO_ID).sort("ts", -1).to_list(limit)

    async def find_by_id(self, alert_id: str) -> Optional[dict]:
        return await self.col.find_one({"id": alert_id}, NO_ID)

    async def acknowledge(self, alert_id: str, actor_email: str, ts: str) -> None:
        await self.col.update_one(
            {"id": alert_id},
            {"$set": {"acknowledged": True, "acknowledged_by": actor_email, "acknowledged_at": ts}},
        )

    async def acknowledge_all_for_device(self, device_id: str, actor_email: str, ts: str) -> int:
        res = await self.col.update_many(
            {"device_id": device_id, "acknowledged": False},
            {"$set": {"acknowledged": True, "acknowledged_by": actor_email, "acknowledged_at": ts}},
        )
        return res.modified_count


class EventRepository:
    def __init__(self, db):
        self.col = db.events

    async def insert(self, event: dict) -> None:
        await self.col.insert_one(dict(event))
