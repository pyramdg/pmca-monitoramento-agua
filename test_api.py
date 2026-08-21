"""
Testes unitários para PMCA API - com fixtures centralizadas no conftest.py
"""

from datetime import timedelta, timezone

from conftest import client
from models import Device, Leitura
from auth_utils import create_refresh_token, hash_api_key, utc_now


class TestAuth:
    """Testes de autenticação"""

    def test_health_check(self):
        """✓ Verificar se a API está online"""
        response = client.get("/health")
        assert response.status_code == 200

    def test_register_success(self):
        """✓ Registrar novo usuário com sucesso"""
        response = client.post(
            "/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "strongpassword123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["is_active"] is True

    def test_register_duplicate_email(self, test_user):
        """✗ Não permitir registrar com email duplicado"""
        response = client.post(
            "/auth/register",
            json={
                "email": "test@example.com",  # Email do test_user
                "password": "password123",
            },
        )
        assert response.status_code == 400

    def test_register_rejects_weak_password(self):
        response = client.post(
            "/auth/register",
            json={"email": "weak@example.com", "password": "123"},
        )
        assert response.status_code == 422

    def test_login_success(self, test_user):
        """✓ Login bem-sucedido retorna JWT"""
        response = client.post(
            "/auth/login",
            json={
                "email": "test@example.com",
                "password": "password123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, test_user):
        """✗ Falhar com senha incorreta"""
        response = client.post(
            "/auth/login",
            json={
                "email": "test@example.com",
                "password": "wrongpassword",
            },
        )
        assert response.status_code == 401

    def test_login_supports_legacy_local_account(self, db_session):
        from auth_utils import hash_password
        from models import User

        user = User(
            email="admin@pmca.local",
            password_hash=hash_password("admin123"),
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        response = client.post(
            "/auth/login",
            json={"email": "admin@pmca.local", "password": "admin123"},
        )
        assert response.status_code == 200

    def test_get_current_user(self, test_user, auth_headers):
        """✓ Obter informações do usuário autenticado"""
        response = client.get("/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"

    def test_get_current_user_invalid_token(self):
        """✗ Falhar com token inválido"""
        headers = {"Authorization": "Bearer invalid_token_123"}
        response = client.post("/auth/me", headers=headers)
        assert response.status_code == 401

    def test_generate_api_key(self, test_user, auth_headers, db_session):
        """✓ Gerar API key para dispositivo"""
        response = client.post("/auth/api-key", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "api_key" in data
        assert "expires_at" in data
        assert data["expires_at"] is None
        assert data["device_name"] == "Meu medidor"
        assert db_session.query(Device).count() == 1

    def test_refresh_token(self, test_user):
        refresh_token = create_refresh_token(test_user.id)
        response = client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_refresh_rejects_access_token(self, auth_headers):
        access_token = auth_headers["Authorization"].split()[1]
        response = client.post("/auth/refresh", json={"refresh_token": access_token})
        assert response.status_code == 401


class TestSensorAPI:
    """Testes da API de recebimento de dados do sensor"""

    def test_send_reading_success(self, test_user, db_session):
        """✓ Enviar leitura do sensor com sucesso"""
        # Gerar API key para o usuário
        api_key = "test_api_key_12345"
        test_user.api_key = hash_api_key(api_key)
        test_user.api_key_expires_at = utc_now() + timedelta(days=1)
        db_session.commit()

        headers = {"Authorization": f"Bearer {api_key}"}
        response = client.post(
            "/api/leitura",
            json={
                "fluxo_litros": 2.5,
                "consumo_total": 150.0,
            },
            headers=headers,
        )
        assert response.status_code == 200

    def test_send_reading_accepts_esp32_utc_timestamp(self, test_user, db_session):
        """O sufixo Z enviado pelo ESP32 deve ser normalizado antes da comparação."""
        api_key = "test_esp32_timestamp_key"
        device = Device(
            user_id=test_user.id,
            name="Medidor ESP32",
            api_key_hash=hash_api_key(api_key),
        )
        db_session.add(device)
        db_session.commit()

        measured_at = (
            utc_now()
            .replace(tzinfo=timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        response = client.post(
            "/api/leitura",
            json={
                "event_id": "ESP32-TIMESTAMP-0001",
                "fluxo_litros": 1.25,
                "consumo_total": 10.5,
                "measured_at": measured_at,
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 200
        assert response.json()["timestamp"] == measured_at.removesuffix("Z")

    def test_send_reading_no_auth(self):
        """✗ Falhar sem API key"""
        response = client.post(
            "/api/leitura",
            json={
                "fluxo_litros": 2.5,
                "consumo_total": 150.0,
            },
        )
        assert response.status_code == 401

    def test_reject_negative_reading(self, test_user, db_session):
        api_key = "test_negative_key"
        test_user.api_key = hash_api_key(api_key)
        db_session.commit()
        response = client.post(
            "/api/leitura",
            json={"fluxo_litros": -1, "consumo_total": 10},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 422

    def test_inactive_user_cannot_send_reading(self, test_user, db_session):
        api_key = "test_inactive_key"
        test_user.api_key = hash_api_key(api_key)
        test_user.is_active = False
        db_session.commit()
        response = client.post(
            "/api/leitura",
            json={"fluxo_litros": 1, "consumo_total": 10},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 403

    def test_list_readings(self, test_user, db_session):
        """✓ Listar leituras do usuário"""
        # Adicionar leituras de teste
        for i in range(3):
            leitura = Leitura(
                user_id=test_user.id,
                fluxo_litros=2.0 + i,
                consumo_total=100.0 + i * 10,
                timestamp=utc_now(),
            )
            db_session.add(leitura)
        db_session.commit()

        # Gerar API key
        api_key = "test_api_key_read"
        test_user.api_key = hash_api_key(api_key)
        db_session.commit()

        headers = {"Authorization": f"Bearer {api_key}"}
        response = client.get("/api/leituras", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    def test_list_readings_validates_limit(self, test_user, db_session):
        api_key = "test_limit_key"
        test_user.api_key = hash_api_key(api_key)
        db_session.commit()
        response = client.get(
            "/api/leituras?limit=501",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 422

    def test_device_key_retries_same_event_without_duplicate(
        self, test_user, db_session
    ):
        api_key = "device-key-for-offline-retry"
        device = Device(
            user_id=test_user.id,
            name="Medidor cozinha",
            api_key_hash=hash_api_key(api_key),
        )
        db_session.add(device)
        db_session.commit()

        payload = {
            "event_id": "AABBCCDDEEFF-1-42",
            "fluxo_litros": 1.75,
            "consumo_total": 20.5,
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        first = client.post("/api/leitura", json=payload, headers=headers)
        retry = client.post("/api/leitura", json=payload, headers=headers)

        assert first.status_code == 200
        assert retry.status_code == 200
        assert first.json()["id"] == retry.json()["id"]
        assert db_session.query(Leitura).count() == 1
        db_session.refresh(device)
        assert device.last_seen_at is not None


class TestDashboard:
    """Testes do dashboard"""

    def test_resumo_empty(self, test_user, auth_headers):
        """✓ Resumo com nenhuma leitura"""
        response = client.get("/dashboard/resumo", headers=auth_headers)
        assert response.status_code == 200

    def test_resumo_with_readings(self, test_user, db_session, auth_headers):
        """✓ Resumo com leituras"""
        # Adicionar leituras
        for i in range(3):
            leitura = Leitura(
                user_id=test_user.id,
                fluxo_litros=2.0 + i,
                consumo_total=100.0 + i * 50,
                timestamp=utc_now(),
            )
            db_session.add(leitura)
        db_session.commit()

        response = client.get("/dashboard/resumo", headers=auth_headers)
        assert response.status_code == 200

    def test_historico(self, test_user, db_session, auth_headers):
        """✓ Obter histórico de leituras"""
        # Adicionar leituras
        for i in range(5):
            leitura = Leitura(
                user_id=test_user.id,
                fluxo_litros=2.0,
                consumo_total=100.0,
                timestamp=utc_now(),
            )
            db_session.add(leitura)
        db_session.commit()

        response = client.get("/dashboard/historico?dias=7", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5


def test_dashboard_web_is_available():
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Cada litro conta" in response.text


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
