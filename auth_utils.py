"""
Utilitários de autenticação: JWT, bcrypt password hashing, etc.
"""

import secrets
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import hashlib

from config import SECRET_KEY

# ==================== PASSWORD HASHING ====================

# Usar pbkdf2 como fallback se bcrypt falhar
try:
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    USE_PASSLIB = True
except Exception:
    USE_PASSLIB = False


def hash_password(password: str) -> str:
    """Hash de senha com pbkdf2 (seguro)"""
    if USE_PASSLIB:
        return pwd_context.hash(password)
    else:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), 310000
        ).hex()
        return f"pbkdf2_sha256${salt}${digest}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verificar se a senha bate com o hash"""
    if USE_PASSLIB:
        return pwd_context.verify(plain_password, hashed_password)
    else:
        try:
            algorithm, salt, expected = hashed_password.split("$", 2)
            if algorithm != "pbkdf2_sha256":
                return False
            actual = hashlib.pbkdf2_hmac(
                "sha256", plain_password.encode(), salt.encode(), 310000
            ).hex()
            return secrets.compare_digest(actual, expected)
        except ValueError:
            return False


def utc_now() -> datetime:
    """Retorna UTC sem timezone para compatibilidade com colunas SQLite atuais."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_naive(value: datetime) -> datetime:
    """Normaliza datas externas para UTC sem timezone, como usado pelo banco."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def hash_api_key(api_key: str) -> str:
    """Gera o valor persistido da API key; a chave original só é exibida uma vez."""
    return hashlib.sha256(api_key.encode()).hexdigest()


# ==================== JWT TOKENS ====================

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 24 * 60  # 24 horas
REFRESH_TOKEN_EXPIRE_DAYS = 30


def create_access_token(
    data: Dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """
    Criar token JWT (access token).

    Args:
        data: Claims do token (e.g., {"sub": user_id, "email": email})
        expires_delta: Tempo de expiração customizado

    Returns:
        Token JWT codificado
    """
    to_encode = data.copy()

    if expires_delta:
        expire = utc_now() + expires_delta
    else:
        expire = utc_now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": utc_now(), "type": "access"})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(user_id: int) -> str:
    """
    Criar refresh token (validade maior).

    Args:
        user_id: ID do usuário

    Returns:
        Refresh token JWT
    """
    data = {"sub": str(user_id), "type": "refresh"}
    expire = utc_now() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    data.update({"exp": expire, "iat": utc_now()})

    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodificar JWT e extrair claims.

    Args:
        token: Token JWT

    Returns:
        Dicionário com claims se válido, None se inválido/expirado
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None  # Token expirado
    except jwt.InvalidTokenError:
        return None  # Token inválido


def extract_user_id_from_token(
    token: str, expected_type: Optional[str] = "access"
) -> Optional[int]:
    """Extrair user_id do token JWT"""
    payload = decode_token(token)
    if not payload:
        return None

    if expected_type and payload.get("type") != expected_type:
        return None

    user_id_str = payload.get("sub")
    if user_id_str:
        try:
            return int(user_id_str)
        except ValueError:
            return None
    return None
