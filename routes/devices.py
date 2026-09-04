import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth_utils import hash_api_key, utc_now
from config import API_KEY_EXPIRATION, DEVICE_ONLINE_TIMEOUT_SECONDS
from database import get_db
from dependencies import get_current_user
from models import Device, User
from schemas import APIKeyResponse, DeviceCreate, DeviceResponse, DeviceUpdate

router = APIRouter(prefix="/devices", tags=["devices"])
MAX_DEVICES_PER_USER = 10


def owned_device(device_id: int, user_id: int, db: Session) -> Device:
    device = (
        db.query(Device)
        .filter(Device.id == device_id, Device.user_id == user_id)
        .first()
    )
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dispositivo não encontrado",
        )
    return device


def new_api_key(device: Device) -> str:
    api_key = secrets.token_urlsafe(32)
    device.api_key_hash = hash_api_key(api_key)
    device.api_key_expires_at = (
        utc_now() + timedelta(seconds=API_KEY_EXPIRATION)
        if API_KEY_EXPIRATION > 0
        else None
    )
    device.is_active = True
    device.last_seen_at = None
    device.continuous_flow_since = None
    return api_key


def device_response(device: Device) -> dict:
    seconds_since_contact = (
        max(0, int((utc_now() - device.last_seen_at).total_seconds()))
        if device.last_seen_at
        else None
    )
    if not device.is_active:
        device_status = "desativado"
    elif seconds_since_contact is None:
        device_status = "aguardando"
    elif seconds_since_contact <= DEVICE_ONLINE_TIMEOUT_SECONDS:
        device_status = "online"
    else:
        device_status = "offline"
    return {
        "id": device.id,
        "name": device.name,
        "is_active": device.is_active,
        "api_key_expires_at": device.api_key_expires_at,
        "last_seen_at": device.last_seen_at,
        "calculated_consumption": device.calculated_consumption,
        "created_at": device.created_at,
        "status": device_status,
        "seconds_since_contact": seconds_since_contact,
        "firmware_version": device.firmware_version,
        "wifi_rssi": device.wifi_rssi,
        "pending_queue": device.pending_queue,
    }


@router.get("", response_model=list[DeviceResponse])
def list_devices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    devices = (
        db.query(Device)
        .filter(Device.user_id == current_user.id)
        .order_by(Device.created_at.asc(), Device.id.asc())
        .all()
    )
    return [device_response(device) for device in devices]


@router.post("", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
def create_device(
    data: DeviceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = db.query(Device).filter(Device.user_id == current_user.id).count()
    if count >= MAX_DEVICES_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Limite de dispositivos atingido",
        )

    clean_name = data.name.strip()
    if not clean_name:
        raise HTTPException(status_code=422, detail="Informe o nome do dispositivo")

    device = Device(
        user_id=current_user.id,
        name=clean_name,
        api_key_hash="pending",
    )
    api_key = new_api_key(device)
    db.add(device)
    db.commit()
    db.refresh(device)
    return {
        "api_key": api_key,
        "device_id": device.id,
        "device_name": device.name,
        "expires_at": device.api_key_expires_at,
    }


@router.patch("/{device_id}", response_model=DeviceResponse)
def update_device(
    device_id: int,
    data: DeviceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = owned_device(device_id, current_user.id, db)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        changes["name"] = changes["name"].strip()
        if not changes["name"]:
            raise HTTPException(status_code=422, detail="Informe o nome do dispositivo")
    for field, value in changes.items():
        setattr(device, field, value)
    if changes.get("is_active") is False:
        device.continuous_flow_since = None
    db.commit()
    db.refresh(device)
    return device_response(device)


@router.post("/{device_id}/api-key", response_model=APIKeyResponse)
def rotate_device_key(
    device_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = owned_device(device_id, current_user.id, db)
    api_key = new_api_key(device)
    db.commit()
    db.refresh(device)
    return {
        "api_key": api_key,
        "device_id": device.id,
        "device_name": device.name,
        "expires_at": device.api_key_expires_at,
    }
