from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status, Header
from sqlalchemy.orm import Session

from database import get_db
from models import Device, User, Leitura
from schemas import LeituraCreate, LeituraResponse
from auth_utils import hash_api_key, utc_naive, utc_now
from config import LEAK_FLOW_THRESHOLD_L_MIN, LEAK_READING_MAX_GAP_SECONDS

router = APIRouter(prefix="/api", tags=["sensor"])


def verify_api_key(authorization: str = Header(None), db: Session = Depends(get_db)):
    """Verificar API key no header Authorization"""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="API key ausente"
        )

    # Espera formato: "Bearer <api_key>"
    try:
        scheme, api_key = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Formato de Authorization inválido",
        )

    key_hash = hash_api_key(api_key)
    device = db.query(Device).filter(Device.api_key_hash == key_hash).first()
    user = device.user if device else None

    # Compatibilidade temporária com chaves criadas antes da tabela de aparelhos.
    if not user:
        user = db.query(User).filter(User.api_key == key_hash).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Usuário desativado"
        )

    # Verificar expiração
    expires_at = device.api_key_expires_at if device else user.api_key_expires_at
    if expires_at and utc_now() > expires_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="API key expirada"
        )

    if device and not device.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Dispositivo desativado"
        )

    return user, device


@router.post("/leitura", response_model=LeituraResponse)
def receber_leitura(
    leitura: LeituraCreate,
    db: Session = Depends(get_db),
    identity: tuple[User, Device | None] = Depends(verify_api_key),
):
    """
    Receber leitura do sensor ESP32.

    Exemplo curl:
    ```
    curl -X POST "http://localhost:8000/api/leitura" \\
      -H "Authorization: Bearer <sua-api-key>" \\
      -H "Content-Type: application/json" \\
      -d '{"fluxo_litros": 2.4, "consumo_total": 150.2}'
    ```
    """
    current_user, device = identity
    if device:
        # Serializa atualizações concorrentes do mesmo medidor para que dois
        # envios simultâneos não somem o mesmo intervalo incorretamente.
        device = (
            db.query(Device).filter(Device.id == device.id).with_for_update().first()
        )

    if leitura.event_id and device:
        existente = (
            db.query(Leitura)
            .filter(
                Leitura.device_id == device.id,
                Leitura.event_id == leitura.event_id,
            )
            .first()
        )
        if existente:
            # Uma repetição também prova que o aparelho está ligado e conseguiu
            # alcançar a API, mesmo que a medição já tenha sido persistida.
            device.last_seen_at = utc_now()
            db.commit()
            return existente

    # O ESP32 envia ISO 8601 com sufixo Z (timezone-aware), enquanto as colunas
    # atuais do banco armazenam UTC sem timezone. Normalize antes de comparar e
    # persistir para que ambos os formatos sejam aceitos com segurança.
    measured_at = utc_naive(leitura.measured_at) if leitura.measured_at else utc_now()
    # Evita que um relógio incorreto no ESP grave datas absurdamente futuras.
    if measured_at > utc_now() + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="Horário da medição inválido")

    previous_reading = None
    volume_delta = 0.0
    calculated_consumption = leitura.consumo_total

    if device:
        previous_reading = (
            db.query(Leitura)
            .filter(Leitura.device_id == device.id)
            .order_by(Leitura.timestamp.desc(), Leitura.id.desc())
            .first()
        )
        previous_total = device.last_reported_total
        if previous_total is None:
            # Na primeira leitura, adota o total já guardado pelo ESP32 como
            # ponto inicial. Depois disso soma somente o volume de cada intervalo.
            calculated_consumption = max(
                float(device.calculated_consumption or 0), leitura.consumo_total
            )
        elif leitura.consumo_total + 0.001 >= previous_total:
            volume_delta = max(0.0, leitura.consumo_total - previous_total)
            calculated_consumption = (
                float(device.calculated_consumption or 0) + volume_delta
            )
        else:
            # O contador bruto diminuiu: o ESP reiniciou ou perdeu seu total.
            # O servidor preserva o histórico e soma apenas o novo ciclo.
            volume_delta = leitura.consumo_total
            calculated_consumption = (
                float(device.calculated_consumption or 0) + volume_delta
            )

        device.last_reported_total = leitura.consumo_total
        device.calculated_consumption = calculated_consumption
        if leitura.firmware_version is not None:
            device.firmware_version = leitura.firmware_version
        if leitura.wifi_rssi is not None:
            device.wifi_rssi = leitura.wifi_rssi
        if leitura.queue_depth is not None:
            device.pending_queue = leitura.queue_depth

        if leitura.fluxo_litros >= LEAK_FLOW_THRESHOLD_L_MIN:
            gap_seconds = (
                (measured_at - previous_reading.timestamp).total_seconds()
                if previous_reading
                else None
            )
            if (
                device.continuous_flow_since is None
                or gap_seconds is None
                or gap_seconds < 0
                or gap_seconds > LEAK_READING_MAX_GAP_SECONDS
            ):
                device.continuous_flow_since = measured_at
        else:
            device.continuous_flow_since = None

    nova_leitura = Leitura(
        user_id=current_user.id,
        device_id=device.id if device else None,
        event_id=leitura.event_id,
        fluxo_litros=leitura.fluxo_litros,
        consumo_total=leitura.consumo_total,
        volume_delta=volume_delta,
        calculated_consumption=calculated_consumption,
        timestamp=measured_at,
        received_at=utc_now(),
    )

    if device:
        device.last_seen_at = utc_now()

    db.add(nova_leitura)
    db.commit()
    db.refresh(nova_leitura)

    return nova_leitura


@router.get("/leituras", response_model=list[LeituraResponse])
def listar_leituras(
    db: Session = Depends(get_db),
    identity: tuple[User, Device | None] = Depends(verify_api_key),
    limit: int = Query(default=100, ge=1, le=500),
):
    """
    Listar últimas leituras do usuário autenticado.

    Query params:
    - limit: Número máximo de registros (default: 100)
    """
    current_user, _ = identity
    leituras = (
        db.query(Leitura)
        .filter(Leitura.user_id == current_user.id)
        .order_by(Leitura.timestamp.desc())
        .limit(limit)
        .all()
    )

    return leituras
