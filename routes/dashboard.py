from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth_utils import extract_user_id_from_token, utc_now
from config import (
    DEVICE_ONLINE_TIMEOUT_SECONDS,
    LEAK_DURATION_MINUTES,
    LEAK_READING_MAX_GAP_SECONDS,
)
from database import get_db
from models import Device, User, Leitura
from schemas import LeituraResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> User:
    """Obtém o usuário autenticado a partir de um JWT Bearer válido."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT não fornecido",
        )

    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Formato de Authorization inválido",
        ) from error

    user_id = extract_user_id_from_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT inválido ou expirado",
        )

    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado ou desativado",
        )

    return user


@router.get("/resumo")
def resumo_consumo(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Resumo de consumo: total, último fluxo, média do dia.
    """
    # Última leitura
    ultima_leitura = (
        db.query(Leitura)
        .filter(Leitura.user_id == current_user.id)
        .order_by(Leitura.timestamp.desc())
        .first()
    )

    # Leituras de hoje
    now = utc_now()
    hoje = now.date()
    leituras_hoje = (
        db.query(Leitura)
        .filter(
            Leitura.user_id == current_user.id,
            func.date(Leitura.timestamp) == hoje,
        )
        .all()
    )

    media_hoje = (
        sum(leitura.fluxo_litros for leitura in leituras_hoje) / len(leituras_hoje)
        if leituras_hoje
        else 0
    )

    inicio_hoje = now.replace(hour=0, minute=0, second=0, microsecond=0)
    inicio_mes = inicio_hoje.replace(day=1)
    consumo_hoje = (
        db.query(func.coalesce(func.sum(Leitura.volume_delta), 0.0))
        .filter(
            Leitura.user_id == current_user.id,
            Leitura.timestamp >= inicio_hoje,
        )
        .scalar()
    )
    consumo_mes = (
        db.query(func.coalesce(func.sum(Leitura.volume_delta), 0.0))
        .filter(
            Leitura.user_id == current_user.id,
            Leitura.timestamp >= inicio_mes,
        )
        .scalar()
    )

    device = (
        db.query(Device)
        .filter(Device.user_id == current_user.id, Device.is_active.is_(True))
        .order_by(Device.last_seen_at.desc(), Device.created_at.desc())
        .first()
    )

    # Contas antigas podem ter leituras sem um registro em devices. Nesse caso,
    # a recepção mais recente ainda serve como indicação de conectividade.
    last_contact = (
        device.last_seen_at
        if device
        else (ultima_leitura.received_at if ultima_leitura else None)
    )
    seconds_since_contact = (
        max(0, int((now - last_contact).total_seconds())) if last_contact else None
    )

    if not device and not ultima_leitura:
        device_status = "nao_configurado"
    elif last_contact is None:
        device_status = "aguardando"
    elif seconds_since_contact <= DEVICE_ONLINE_TIMEOUT_SECONDS:
        device_status = "online"
    else:
        device_status = "offline"

    latest_flow = ultima_leitura.fluxo_litros if ultima_leitura else 0
    if not ultima_leitura:
        water_status = "sem_dados"
    elif device_status != "online":
        water_status = "desconhecido"
    elif latest_flow > 0.01:
        water_status = "fluxo_detectado"
    else:
        water_status = "sem_fluxo"

    measurement_age = (
        max(0, int((now - ultima_leitura.timestamp).total_seconds()))
        if ultima_leitura
        else None
    )
    continuous_flow_seconds = (
        max(0, int((now - device.continuous_flow_since).total_seconds()))
        if device and device.continuous_flow_since
        else 0
    )
    possible_leak = bool(
        device_status == "online"
        and measurement_age is not None
        and measurement_age <= LEAK_READING_MAX_GAP_SECONDS
        and continuous_flow_seconds >= LEAK_DURATION_MINUTES * 60
    )

    if device and device.last_reported_total is not None:
        reliable_total = float(device.calculated_consumption or 0)
    elif ultima_leitura and ultima_leitura.calculated_consumption is not None:
        reliable_total = ultima_leitura.calculated_consumption
    else:
        reliable_total = ultima_leitura.consumo_total if ultima_leitura else 0

    return {
        "consumo_total": round(reliable_total, 3),
        "consumo_hoje": round(float(consumo_hoje or 0), 3),
        "consumo_mes": round(float(consumo_mes or 0), 3),
        "ultimo_fluxo": latest_flow,
        "media_hoje": round(media_hoje, 2),
        "timestamp_ultima": ultima_leitura.timestamp if ultima_leitura else None,
        "leituras_hoje": len(leituras_hoje),
        "dispositivo": {
            "nome": device.name if device else "Meu medidor",
            "status": device_status,
            "ultima_comunicacao": last_contact,
            "segundos_desde_comunicacao": seconds_since_contact,
            "limite_online_segundos": DEVICE_ONLINE_TIMEOUT_SECONDS,
            "situacao_agua": water_status,
            "possivel_vazamento": possible_leak,
            "fluxo_continuo_minutos": continuous_flow_seconds // 60,
            "limite_vazamento_minutos": LEAK_DURATION_MINUTES,
        },
    }


@router.get("/historico", response_model=list[LeituraResponse])
def historico_leituras(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    dias: int = Query(default=7, ge=1, le=365),
):
    """
    Histórico de leituras dos últimos N dias.

    Query params:
    - dias: Número de dias no passado (default: 7)
    - limit: Limite de registros (omitir para trazer tudo)
    """
    data_inicio = utc_now() - timedelta(days=dias)

    leituras = (
        db.query(Leitura)
        .filter(
            Leitura.user_id == current_user.id,
            Leitura.timestamp >= data_inicio,
        )
        .order_by(Leitura.timestamp.asc())
        .all()
    )

    return leituras
