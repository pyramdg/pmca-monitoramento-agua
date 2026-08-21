from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from datetime import timedelta
import secrets

from database import get_db
from models import User
from schemas import (
    UserCreate,
    UserResponse,
    LoginRequest,
    TokenResponse,
    APIKeyResponse,
    RefreshTokenRequest,
)
from config import API_KEY_EXPIRATION
from auth_utils import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    extract_user_id_from_token,
    hash_api_key,
    utc_now,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """
    Registrar novo usuário.

    Exemplo:
    ```
    curl -X POST "http://localhost:8000/auth/register" \\
      -H "Content-Type: application/json" \\
      -d '{"email":"user@example.com","password":"senha123"}'
    ```
    """
    # Validar se email já existe
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email já registrado",
        )

    # Criar novo usuário com senha hasheada
    user = User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.post("/login", response_model=TokenResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    """
    Login com email e senha, retorna JWT access token.

    Exemplo:
    ```
    curl -X POST "http://localhost:8000/auth/login" \\
      -H "Content-Type: application/json" \\
      -d '{"email":"user@example.com","password":"senha123"}'
    ```
    """
    user = db.query(User).filter(User.email == credentials.email).first()

    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha inválidos",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário desativado",
        )

    # Criar JWT tokens
    access_token = create_access_token(data={"sub": str(user.id), "email": user.email})
    refresh_token = create_refresh_token(user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user,
    }


@router.post("/refresh")
def refresh_access_token(
    token_data: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    """
    Renovar access token usando refresh token.

    Exemplo:
    ```
    curl -X POST "http://localhost:8000/auth/refresh" \\
      -H "Content-Type: application/json" \\
      -d '{"refresh_token":"seu-refresh-token"}'
    ```
    """
    user_id = extract_user_id_from_token(
        token_data.refresh_token, expected_type="refresh"
    )

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido ou expirado",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado ou desativado",
        )

    new_access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )

    return {
        "access_token": new_access_token,
        "token_type": "bearer",
    }


@router.post("/api-key", response_model=APIKeyResponse)
def generate_api_key(
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):
    """
    Gerar API key para o dispositivo ESP32 usando JWT.

    Header obrigatório:
    - Authorization: "Bearer <seu-jwt-access-token>"

    Exemplo:
    ```
    curl -X POST "http://localhost:8000/auth/api-key" \\
      -H "Authorization: Bearer seu-access-token-jwt"
    ```
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT não fornecido",
        )

    # Extrair token do header "Bearer <token>"
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Formato de Authorization inválido",
        )

    # Validar token JWT
    user_id = extract_user_id_from_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT inválido ou expirado",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado",
        )

    # Gerar API key para dispositivo
    api_key = secrets.token_urlsafe(32)
    expires_at = utc_now() + timedelta(seconds=API_KEY_EXPIRATION)

    user.api_key = hash_api_key(api_key)
    user.api_key_expires_at = expires_at

    db.commit()

    return {"api_key": api_key, "expires_at": expires_at}


@router.get("/me", response_model=UserResponse)
def get_current_user(
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):
    """
    Obter informações do usuário autenticado (via JWT).

    Exemplo:
    ```
    curl -X GET "http://localhost:8000/auth/me" \\
      -H "Authorization: Bearer seu-access-token"
    ```
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT não fornecido",
        )

    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Formato de Authorization inválido",
        )

    user_id = extract_user_id_from_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT inválido ou expirado",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado",
        )

    return user


@router.post("/me", response_model=UserResponse, include_in_schema=False)
def get_current_user_legacy(
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):
    """Compatibilidade temporária com clientes que ainda usam POST."""
    return get_current_user(db=db, authorization=authorization)
