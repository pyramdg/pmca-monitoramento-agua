from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path

from config import ALLOWED_ORIGINS, DEBUG, ENV
from database import engine, init_db
from sqlalchemy import text
from routes import auth, sensor, dashboard, devices, settings

# Inicializar banco de dados
init_db()


# Lifecycle events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicialização e limpeza"""
    print("🚀 PMCA inicializando...")
    yield
    print("🛑 PMCA finalizando...")


# Criar aplicação FastAPI
app = FastAPI(
    title="PMCA - Monitoramento de Consumo de Água",
    description="API para receber e monitorar dados de consumo de água via ESP32",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - Permitir requisições do frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if ENV != "development":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    if request.url.path == "/dashboard":
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
    if request.url.path in {"/dashboard", "/styles.css", "/app.js"}:
        # O painel evolui junto com o servidor; force o navegador a validar a
        # versão para não misturar HTML novo com CSS ou JavaScript antigos.
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


# Registrar rotas
app.include_router(auth.router)
app.include_router(sensor.router)
app.include_router(dashboard.router)
app.include_router(devices.router)
app.include_router(settings.router)

WEB_DIR = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


# Health check
@app.get("/health")
def health_check():
    """Verificar se a API está online"""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            {"status": "error", "message": "Banco de dados indisponível"},
            status_code=503,
        )
    return JSONResponse({"status": "ok", "message": "PMCA está online"})


# Root
@app.get("/")
def root():
    """Endpoint raiz"""
    return {
        "message": "PMCA - Monitoramento de Consumo de Água",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/dashboard", include_in_schema=False)
def dashboard_web():
    """Interface web do monitoramento."""
    return FileResponse(WEB_DIR / "index.html")


# Estes atalhos mantêm os arquivos relativos do painel funcionando tanto quando
# servidos pela aplicação quanto quando o HTML é aberto localmente por engano.
@app.get("/styles.css", include_in_schema=False)
def dashboard_styles():
    return FileResponse(WEB_DIR / "styles.css", media_type="text/css")


@app.get("/app.js", include_in_schema=False)
def dashboard_script():
    return FileResponse(WEB_DIR / "app.js", media_type="text/javascript")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=DEBUG)
