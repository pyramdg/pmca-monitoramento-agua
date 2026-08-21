#!/usr/bin/env python3
"""
Quick Start Script - Configurar e testar PMCA em 2 minutos

Este script:
1. Verifica se temos tudo instalado
2. Cria o banco de dados
3. Migra dados do CSV
4. Mostra instruções de teste
"""

import sys
import os
import shutil
import subprocess


def check_python():
    """Verificar versão Python"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ required!")
        sys.exit(1)
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor} OK")


def check_env_file():
    """Verificar se .env existe"""
    if not os.path.exists(".env"):
        print("📝 Criando .env...")
        shutil.copyfile(".env.example", ".env")
        print("✓ .env criado")
    else:
        print("✓ .env já existe")


def run_migration():
    """Executar migração CSV"""
    print("\n🔄 Migrando dados do CSV...")
    try:
        result = subprocess.run(
            [sys.executable, "migrate_csv_to_db.py"],
            capture_output=True,
            text=True,
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"⚠️  {result.stderr}")
    except Exception as e:
        print(f"❌ Erro: {e}")


def run_tests():
    """Executar testes"""
    print("\n🧪 Executando testes...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "test_api.py", "-v", "--tb=short"],
            capture_output=True,
            text=True,
        )
        print(result.stdout)
        if result.returncode == 0:
            print("\n✅ Testes passaram!")
        else:
            print(f"\n⚠️  Alguns testes falharam:\n{result.stderr}")
    except Exception as e:
        print(f"❌ Erro: {e}")


def show_instructions():
    """Mostrar instruções finais"""
    print("\n" + "=" * 60)
    print("🚀 QUICK START - Próximos Passos")
    print("=" * 60)
    print("""
1️⃣  INICIAR SERVIDOR:
    python main.py

2️⃣  ACESSAR DOCUMENTAÇÃO:
    http://localhost:8000/docs

3️⃣  TESTAR ENDPOINTS:
    # Registrar
    curl -X POST "http://localhost:8000/auth/register" \\
      -H "Content-Type: application/json" \\
      -d '{"email":"seu@email.com","password":"senha123"}'

    # Login
    curl -X POST "http://localhost:8000/auth/login" \\
      -H "Content-Type: application/json" \\
      -d '{"email":"seu@email.com","password":"senha123"}'

4️⃣  EXECUTAR TESTES A QUALQUER HORA:
    pytest test_api.py -v

5️⃣  PRÓXIMA ETAPA:
    Veja README.md para plano de evolução

Se um usuário administrador for criado, a senha inicial será mostrada uma única
vez pela migração. Ela não fica armazenada no código-fonte.
""")
    print("=" * 60)


def main():
    print("=" * 60)
    print("🔧 PMCA - Quick Start Setup")
    print("=" * 60)
    print()

    check_python()
    check_env_file()
    run_migration()
    run_tests()
    show_instructions()


if __name__ == "__main__":
    main()
