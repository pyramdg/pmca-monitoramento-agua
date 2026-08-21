import os
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
SECRET_KEY = os.getenv(
    "SECRET_KEY", "your-secret-key-change-in-production"  # MUDE EM PRODUÇÃO!
)

if ENV != "development" and SECRET_KEY == "your-secret-key-change-in-production":
    raise RuntimeError(
        "SECRET_KEY deve ser configurada fora do ambiente de desenvolvimento"
    )

# API
API_KEY_EXPIRATION = 30 * 24 * 60 * 60  # 30 dias em segundos

# CORS
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5000"
).split(",")
