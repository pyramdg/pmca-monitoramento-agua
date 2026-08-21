"""
Configuração centralizada para testes - pytest conftest.py

Garante que:
1. Banco em memória é criado UMA VEZ para todos os testes
2. Cada teste roda com dados limpos (truncate entre testes)
3. Todas as sessões usam o mesmo engine (StaticPool)
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth_utils import create_access_token, hash_password
from database import Base, get_db
from main import app
from models import User

# 1. Criar engine em memória COM pool estático (garante reutilização)
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)

# 2. Criar todas as tabelas UMA VEZ (fixtures usarão este engine)
Base.metadata.create_all(bind=engine)

# 3. Factory de sessão para testes
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Dependency override: retorna sessão do banco de testes"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Aplicar override ao app
app.dependency_overrides[get_db] = override_get_db

# Cliente HTTP compartilhado
client = TestClient(app)


# ==================== FIXTURES PYTEST ====================


@pytest.fixture(autouse=True)
def cleanup_db():
    """
    Limpar banco ANTES e DEPOIS de cada teste.
    autouse=True garante que roda automaticamente.
    """
    # ANTES do teste: truncar tabelas
    with engine.connect() as conn:
        # Desabilitar constraints no SQLite
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f"DELETE FROM {table.name}"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.commit()

    yield  # Executar o teste aqui

    # DEPOIS do teste: truncar novamente
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f"DELETE FROM {table.name}"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.commit()


@pytest.fixture
def db_session():
    """Sessão do banco para testes que precisam acesso direto"""
    db = TestingSessionLocal()
    yield db
    db.close()


@pytest.fixture
def test_user(db_session):
    """Criar usuário de teste"""
    user = User(
        email="test@example.com",
        password_hash=hash_password("password123"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user):
    """Gerar headers com JWT válido"""
    token = create_access_token(
        data={"sub": str(test_user.id), "email": test_user.email}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client_with_auth(auth_headers):
    """Cliente HTTP com headers de autenticação"""
    test_client = TestClient(app)
    test_client.headers.update(auth_headers)
    return test_client
