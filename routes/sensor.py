from fastapi import APIRouter, Depends, HTTPException, Query, status, Header
from sqlalchemy.orm import Session

from database import get_db
from models import User, Leitura
from schemas import LeituraCreate, LeituraResponse
from auth_utils import hash_api_key, utc_now

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

    # Procurar usuário com essa API key
    user = db.query(User).filter(User.api_key == hash_api_key(api_key)).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Usuário desativado"
        )

    # Verificar expiração
    if user.api_key_expires_at and utc_now() > user.api_key_expires_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="API key expirada"
        )

    return user


@router.post("/leitura", response_model=LeituraResponse)
def receber_leitura(
    leitura: LeituraCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
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
    # Criar nova leitura
    nova_leitura = Leitura(
        user_id=current_user.id,
        fluxo_litros=leitura.fluxo_litros,
        consumo_total=leitura.consumo_total,
        timestamp=utc_now(),
    )

    db.add(nova_leitura)
    db.commit()
    db.refresh(nova_leitura)

    return nova_leitura


@router.get("/leituras", response_model=list[LeituraResponse])
def listar_leituras(
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
    limit: int = Query(default=100, ge=1, le=500),
):
    """
    Listar últimas leituras do usuário autenticado.

    Query params:
    - limit: Número máximo de registros (default: 100)
    """
    leituras = (
        db.query(Leitura)
        .filter(Leitura.user_id == current_user.id)
        .order_by(Leitura.timestamp.desc())
        .limit(limit)
        .all()
    )

    return leituras
