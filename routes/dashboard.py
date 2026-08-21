from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth_utils import extract_user_id_from_token, utc_now
from database import get_db
from models import User, Leitura
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

    if not ultima_leitura:
        return {
            "consumo_total": 0,
            "ultimo_fluxo": 0,
            "media_hoje": 0,
            "timestamp_ultima": None,
        }

    # Leituras de hoje
    hoje = utc_now().date()
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

    return {
        "consumo_total": ultima_leitura.consumo_total,
        "ultimo_fluxo": ultima_leitura.fluxo_litros,
        "media_hoje": round(media_hoje, 2),
        "timestamp_ultima": ultima_leitura.timestamp,
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
