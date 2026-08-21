# 🚰 PMCA — Monitoramento de Consumo de Água

Aplicação FastAPI para receber, armazenar e monitorar dados de consumo de água via ESP32 com segurança de produção.

**Status:** ✅ **Etapa 1 Completa** (Estrutura + JWT + Testes + Migração)

---

## 📋 Conteúdo

- [Estrutura](#-estrutura-do-projeto)
- [Começar](#-como-começar)
- [Rotas](#-rotas-disponíveis)
- [Autenticação JWT](#-autenticação-jwt)
- [Testes](#-testes-unitários)
- [Migração de Dados](#-migração-de-dados)
- [Próximos Passos](#-próximos-passos)

---

## 🏗️ Estrutura do Projeto

```
pmca/
├── main.py                  ← Entry point (FastAPI app)
├── config.py                ← Variáveis de ambiente
├── database.py              ← Setup SQLAlchemy + SessionLocal
├── models.py                ← Modelos (User, Leitura)
├── schemas.py               ← Validação Pydantic
├── auth_utils.py            ← JWT + bcrypt utilities ⭐ NOVO
├── routes/
│   ├── auth.py              ← /auth/* (register, login, JWT, API key)
│   ├── sensor.py            ← /api/leitura (ESP32 envia dados)
│   └── dashboard.py         ← /dashboard/* (resumo, histórico)
├── test_api.py              ← Testes unitários ⭐ NOVO
├── migrate_csv_to_db.py     ← Script de migração CSV→SQLite ⭐ NOVO
├── requirements.txt         ← Dependências
├── .env.example             ← Template de variáveis
├── .gitignore               ← Arquivos ignorados
├── pmca.db                  ← Banco SQLite (gerado)
└── dados.csv                ← Dados históricos (para migração)
```

---

## 🚀 Como Começar

### 1️⃣ Instalar Dependências

```bash
# Navegar para a pasta do projeto
cd pmca

# Criar virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# ou
source venv/bin/activate  # macOS/Linux

# Instalar pacotes
pip install -r requirements.txt
```

### 2️⃣ Configurar .env

```bash
# Copiar template
cp .env.example .env

# Editar .env (ou usar valores padrão para testes)
# Importante em produção:
# - SECRET_KEY: gerar com `python -c "import secrets; print(secrets.token_urlsafe(32))"`
# - DATABASE_URL: PostgreSQL em produção
# - ALLOWED_ORIGINS: seus domínios
```

### 3️⃣ Rodar a Aplicação

```bash
# Iniciar servidor
python main.py

# Ou com uvicorn diretamente
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

✅ **API disponível em:**
- 🌐 http://localhost:8000/
- 📖 **Docs (Swagger):** http://localhost:8000/docs
- 📘 **ReDoc:** http://localhost:8000/redoc

---

## 🔐 Autenticação JWT

A API usa **JWT (JSON Web Tokens)** com **bcrypt** para segurança robusta.

### Fluxo de Autenticação

```
1. POST /auth/register          → Criar conta (email + senha)
2. POST /auth/login             → Obter access_token + refresh_token
3. POST /auth/api-key           → Gerar API key para dispositivo (usando JWT)
4. POST /api/leitura            → ESP32 envia leitura (usando API key)
```

### Tokens

| Token | Validade | Uso |
|-------|----------|-----|
| **access_token** | 24 horas | Autenticação de usuário |
| **refresh_token** | 30 dias | Renovar access_token |
| **api_key** | 30 dias | Autenticação de dispositivo ESP32 |

---

## 📋 Rotas Disponíveis

### 🔑 Autenticação (`/auth`)

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/auth/register` | Registrar novo usuário |
| POST | `/auth/login` | Login (retorna JWT) |
| POST | `/auth/refresh` | Renovar access_token |
| POST | `/auth/api-key` | Gerar API key (para ESP32) |
| POST | `/auth/me` | Obter dados do usuário (requer JWT) |

### 📡 Sensor API (`/api`)

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| POST | `/api/leitura` | Enviar leitura (ESP32) | API key |
| GET | `/api/leituras` | Listar leituras | API key |

### 📊 Dashboard (`/dashboard`)

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| GET | `/dashboard/resumo` | Consumo total + vazão | query param |
| GET | `/dashboard/historico` | Histórico N dias | query param |

---

## 🧪 Testes Unitários

### Executar Testes

```bash
# Todos os testes
pytest test_api.py -v

# Com cobertura
pytest test_api.py -v --cov=.

# Teste específico
pytest test_api.py::TestAuth::test_login_success -v
```

### Cobertura de Testes

✅ **Auth (7 testes)**
- Register (sucesso + duplicate email)
- Login (sucesso + wrong password + nonexistent user)
- JWT (current user + invalid token)
- API Key generation

✅ **Sensor API (4 testes)**
- Send reading (sucesso + no auth + invalid key)
- List readings (com limit)

✅ **Dashboard (3 testes)**
- Resumo (empty + with readings)
- Histórico

---

## 📊 Migração de Dados

Migrar dados do `dados.csv` para o banco SQLite.

### Executar Migração

```bash
# Criar banco + importar dados + criar usuário admin
python migrate_csv_to_db.py

# Saída esperada:
# 🚀 Iniciando migração CSV → SQLite
# ✓ Banco criado/verificado
# ✓ Usuário admin criado: admin@pmca.local
# A senha inicial é exibida uma única vez no terminal.
# ✓ Registros importados: 1
# ✓ Total de leituras no banco: 1
```

**Usuário padrão criado:**
- Email: configurável por `ADMIN_EMAIL`
- Senha: configurável por `ADMIN_PASSWORD` ou gerada automaticamente

---

## 🧑‍💻 Fluxo Completo de Teste (Local)

### 1️⃣ Registrar Usuário

```bash
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123"
  }'

# Resposta:
# {
#   "id": 1,
#   "email": "test@example.com",
#   "is_active": true,
#   "created_at": "2026-08-15T10:00:00"
# }
```

### 2️⃣ Fazer Login (Obter JWT)

```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123"
  }'

# Resposta:
# {
#   "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
#   "token_type": "bearer",
#   "user": { ... }
# }

# Copie o access_token para os próximos passos
export JWT_TOKEN="seu-token-aqui"
```

### 3️⃣ Gerar API Key (para ESP32)

```bash
curl -X POST "http://localhost:8000/auth/api-key" \
  -H "Authorization: Bearer $JWT_TOKEN"

# Resposta:
# {
#   "api_key": "abc123def456...",
#   "expires_at": "2026-09-14T10:00:00"
# }

export API_KEY="sua-api-key-aqui"
```

### 4️⃣ Enviar Leitura (Simular ESP32)

```bash
curl -X POST "http://localhost:8000/api/leitura" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "fluxo_litros": 2.5,
    "consumo_total": 150.0
  }'

# Resposta:
# {
#   "id": 1,
#   "user_id": 1,
#   "fluxo_litros": 2.5,
#   "consumo_total": 150.0,
#   "timestamp": "2026-08-15T10:05:00"
# }
```

### 5️⃣ Obter Resumo

```bash
curl "http://localhost:8000/dashboard/resumo?user_id=1"

# Resposta:
# {
#   "consumo_total": 150.0,
#   "ultimo_fluxo": 2.5,
#   "media_hoje": 2.5,
#   "timestamp_ultima": "2026-08-15T10:05:00"
# }
```

---

## 🔐 Segurança

- ✅ **Senhas**: Hasheadas com bcrypt (nunca em texto puro)
- ✅ **JWT**: HS256, 24h de validade
- ✅ **API Keys**: Para dispositivos (ESP32), 30 dias
- ✅ **CORS**: Configurável por origem
- ⚠️ **TODO**: Rate limiting, logging, monitoramento

---

## 📝 Próximas Etapas

### **Etapa 2** — Autenticação + Banco Completo
- [ ] Integrar JWT em todas as rotas protegidas
- [ ] Testar tudo localmente
- [ ] Criar conftest.py para fixtures compartilhadas
- [ ] Adicionar logging

### **Etapa 3** — Dashboard Web
- [ ] Template HTML + Bootstrap
- [ ] Gráficos com Chart.js
- [ ] Autenticação (sessão + cookies)

### **Etapa 4** — Preparar Produção
- [ ] Docker + docker-compose
- [ ] Variáveis .env robustas
- [ ] Gunicorn + Nginx
- [ ] PostgreSQL

### **Etapa 5** — Deploy
- [ ] Render.com ou Railway.app
- [ ] CI/CD com GitHub Actions
- [ ] Monitoramento

---

## 🛠️ Desenvolvimento

### Formatar Código

```bash
black .
flake8 .
```

### Dependências Principais

| Pacote | Versão | Uso |
|--------|--------|-----|
| FastAPI | 0.109.0 | Web framework |
| SQLAlchemy | 2.0.23 | ORM |
| PyJWT | 2.8.1 | JWT tokens |
| passlib[bcrypt] | 1.7.4 | Password hashing |
| Pydantic | 2.5.2 | Validação |
| pytest | 7.4.3 | Testes |

---

## 📚 Referências

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/)
- [PyJWT](https://pyjwt.readthedocs.io/)
- [Pydantic](https://docs.pydantic.dev/)
- [pytest](https://docs.pytest.org/)

---

**🎉 Etapa 1 ✅ Concluída! Pronto para testes locais e Etapa 2.**
