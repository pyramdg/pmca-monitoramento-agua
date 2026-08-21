import os
import secrets
from dotenv import load_dotenv

load_dotenv()

# Ambiente
ENV = os.getenv("ENV", "development")
DEBUG = ENV == "development"

# Banco de dados
DATABASE_URL = os.getenv(
    "DATABASE_URL", "sqlite:///./pmca.db"  # SQLite local para desenvolvimento
)
# Railway e alguns provedores ainda entregam o prefixo antigo do PostgreSQL.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# Segurança
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if ENV != "development":
        raise RuntimeError(
            "SECRET_KEY deve ser configurada fora do ambiente de desenvolvimento"
        )
    # Desenvolvimento local continua simples, mas sem um segredo público previsível.
    # Tokens locais deixam de valer quando o processo reinicia sem arquivo .env.
    SECRET_KEY = secrets.token_urlsafe(32)

# API
# A chave do aparelho permanece válida até ser trocada ou desativada.
API_KEY_EXPIRATION = int(os.getenv("API_KEY_EXPIRATION", "0"))

# O firmware registra uma leitura a cada 10 segundos. Quatro ciclos e meio sem
# contato são suficientes para sinalizar que o aparelho provavelmente perdeu
# energia ou internet, sem piscar entre online/offline por um atraso pontual.
DEVICE_ONLINE_TIMEOUT_SECONDS = max(
    20, int(os.getenv("DEVICE_ONLINE_TIMEOUT_SECONDS", "45"))
)

# CORS
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5000"
).split(",")
