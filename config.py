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
API_KEY_EXPIRATION = 30 * 24 * 60 * 60  # 30 dias em segundos

# CORS
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5000"
).split(",")
