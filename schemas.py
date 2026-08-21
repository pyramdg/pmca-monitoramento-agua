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
    pass


class LeituraResponse(LeituraBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
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
    expires_at: Optional[datetime] = None
