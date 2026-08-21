#!/usr/bin/env python3
"""
Script de migração: CSV → SQLite

Lê dados.csv e importa para o banco de dados SQLite.
Cria usuário padrão ("admin@pmca.local") se não existir.

Uso:
    python migrate_csv_to_db.py
"""

import csv
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path

from database import SessionLocal, init_db
from models import User, Leitura
from auth_utils import hash_password

CSV_FILE = "dados.csv"
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@pmca.local")


def create_admin_user(db):
    """Criar usuário admin se não existir"""
    existing = db.query(User).filter(User.email == ADMIN_EMAIL).first()
    if existing:
        print(f"✓ Usuário admin já existe: {ADMIN_EMAIL}")
        return existing

    configured_password = os.getenv("ADMIN_PASSWORD")
    initial_password = configured_password or secrets.token_urlsafe(12)

    admin = User(
        email=ADMIN_EMAIL,
        password_hash=hash_password(initial_password),
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    print(f"✓ Usuário admin criado: {ADMIN_EMAIL}")
    if configured_password:
        print("   ✓ Senha carregada da variável ADMIN_PASSWORD")
    else:
        print(f"   Senha inicial gerada: {initial_password}")
        print("   Guarde-a agora; ela não está salva no código.")
    return admin


def migrate_csv_to_db(db):
    """Ler CSV e importar leituras para o banco"""
    if not Path(CSV_FILE).exists():
        print(f"⚠️  Arquivo {CSV_FILE} não encontrado. Pulando migração.")
        return 0

    # Obter usuário admin
    admin = db.query(User).filter(User.email == ADMIN_EMAIL).first()
    if not admin:
        print("❌ Erro: Usuário admin não existe!")
        return 0

    # Ler CSV
    imported_count = 0
    skipped_count = 0

    try:
        with open(CSV_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                try:
                    # Parsear campos
                    timestamp = datetime.strptime(row["data_hora"], "%Y-%m-%d %H:%M:%S")
                    fluxo = float(row["fluxo_litros"])
                    consumo = float(row["consumo_total"])

                    # Verificar se já existe
                    existing = (
                        db.query(Leitura)
                        .filter(
                            Leitura.user_id == admin.id,
                            Leitura.timestamp == timestamp,
                        )
                        .first()
                    )

                    if existing:
                        skipped_count += 1
                        continue

                    # Criar registro
                    leitura = Leitura(
                        user_id=admin.id,
                        fluxo_litros=fluxo,
                        consumo_total=consumo,
                        timestamp=timestamp,
                    )
                    db.add(leitura)
                    imported_count += 1

                except (ValueError, KeyError) as e:
                    print(f"  ⚠️  Linha inválida: {row} ({e})")
                    skipped_count += 1
                    continue

        db.commit()

    except Exception as e:
        print(f"❌ Erro ao ler CSV: {e}")
        db.rollback()
        return 0

    return imported_count


def main():
    """Executar migração"""
    print("=" * 60)
    print("🚀 Iniciando migração CSV → SQLite")
    print("=" * 60)

    # Inicializar banco de dados
    print("\n1️⃣  Inicializando banco de dados...")
    init_db()
    print("   ✓ Banco criado/verificado")

    # Criar session
    db = SessionLocal()

    try:
        # Criar usuário admin
        print("\n2️⃣  Criando/verificando usuário admin...")
        admin = create_admin_user(db)

        # Migrar dados
        print("\n3️⃣  Importando dados do CSV...")
        imported = migrate_csv_to_db(db)

        # Resumo
        print("\n" + "=" * 60)
        print("📊 RESUMO DA MIGRAÇÃO")
        print("=" * 60)
        print(f"✓ Registros importados: {imported}")
        total_leituras = db.query(Leitura).filter(Leitura.user_id == admin.id).count()
        print(f"✓ Total de leituras no banco: {total_leituras}")
        print("=" * 60)

        if imported > 0:
            print("\n✅ Migração concluída com sucesso!")
        else:
            print("\n⚠️  Nenhum registro foi importado (já existiam ou erro).")

    except Exception as e:
        print(f"\n❌ Erro durante migração: {e}")
        db.rollback()
        sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    main()
