from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ==================== USER ====================


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    email: str
    id: int
    is_active: bool
    created_at: datetime


# ==================== LEITURA ====================


class LeituraBase(BaseModel):
    fluxo_litros: float = Field(ge=0)
    consumo_total: float = Field(ge=0)


class LeituraCreate(LeituraBase):
    event_id: Optional[str] = Field(default=None, min_length=8, max_length=96)
    measured_at: Optional[datetime] = None


class LeituraResponse(LeituraBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    device_id: Optional[int] = None
    event_id: Optional[str] = None
    volume_delta: float = 0.0
    calculated_consumption: Optional[float] = None
    timestamp: datetime


# ==================== AUTH ====================


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class LoginRequest(BaseModel):
    # Login aceita contas legadas como admin@pmca.local; novos cadastros usam EmailStr.
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ==================== API KEY ====================


class APIKeyResponse(BaseModel):
    api_key: str
    device_id: int
    device_name: str
    expires_at: Optional[datetime] = None


# ==================== DEVICE ====================


class DeviceCreate(BaseModel):
    name: str = Field(default="Meu medidor", min_length=1, max_length=80)


class DeviceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    is_active: Optional[bool] = None


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_active: bool
    api_key_expires_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    calculated_consumption: float
    created_at: datetime
    status: str = "aguardando"
    seconds_since_contact: Optional[int] = None


# ==================== SETTINGS ====================


class UserSettings(BaseModel):
    monthly_goal_liters: Optional[float] = Field(default=None, gt=0, le=10_000_000)
    water_price_per_m3: Optional[float] = Field(default=None, ge=0, le=100_000)
