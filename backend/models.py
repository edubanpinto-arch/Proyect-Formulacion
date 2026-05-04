"""Pydantic models."""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime, timezone
import uuid


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- Users / Auth ----
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TwoFactorVerifyRequest(BaseModel):
    temp_token: str
    code: str


class TwoFactorEnrollVerifyRequest(BaseModel):
    temp_token: str
    code: str


class ChangePasswordRequest(BaseModel):
    temp_token: Optional[str] = None
    current_password: Optional[str] = None
    new_password: str = Field(min_length=8)


class CreateTransporterRequest(BaseModel):
    email: EmailStr
    name: str
    password: str = Field(min_length=6)


class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str
    password: str = Field(min_length=6)
    role: str = Field(pattern="^(admin|transporter)$")
    must_change_password: bool = True


class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = Field(default=None, pattern="^(admin|transporter)$")
    disabled: Optional[bool] = None
    must_change_password: Optional[bool] = None
    reset_2fa: Optional[bool] = None


class AdminResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=6)
    must_change_password: bool = True


class SelfChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


# ---- Devices ----
class DeviceApproveRequest(BaseModel):
    device_id: str
    name: Optional[str] = None
    transporter_email: Optional[str] = None  # assign owner


class DeviceRejectRequest(BaseModel):
    device_id: str


class TemperatureIngest(BaseModel):
    deviceId: str
    devicePassword: str
    temperature: float
    nonce: Optional[int] = None
    signature: Optional[str] = None


class ToggleHmacRequest(BaseModel):
    device_id: str
    require_hmac: bool


class TransporterAccessRequest(BaseModel):
    device_password: str


# ---- Response helpers ----
class UserPublic(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: str
    must_change_password: bool = False
    totp_enabled: bool = False
