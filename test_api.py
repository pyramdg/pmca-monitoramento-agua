"""
Testes unitários para PMCA API - com fixtures centralizadas no conftest.py
"""

from datetime import timedelta, timezone

from conftest import client
from models import Device, Leitura
from auth_utils import create_refresh_token, hash_api_key, utc_now
from config import LOGIN_MAX_FAILURES


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

    def test_browser_session_uses_protected_refresh_cookie(self, test_user):
        from fastapi.testclient import TestClient
        from main import app

        with TestClient(app) as browser:
            login = browser.post(
                "/auth/login",
                json={"email": "test@example.com", "password": "password123"},
            )
            assert login.status_code == 200
            cookie = login.headers["set-cookie"]
            assert "pmca_refresh=" in cookie
            assert "HttpOnly" in cookie

            refreshed = browser.post("/auth/refresh")
            assert refreshed.status_code == 200
            assert "access_token" in refreshed.json()

            logout = browser.post("/auth/logout")
            assert logout.status_code == 204
            assert browser.post("/auth/refresh").status_code == 401

    def test_login_temporarily_blocks_repeated_failures(self, db_session):
        from auth_utils import hash_password
        from models import User

        email = "rate-limit@example.com"
        db_session.add(
            User(
                email=email,
                password_hash=hash_password("correct-password"),
                is_active=True,
            )
        )
        db_session.commit()

        for _ in range(LOGIN_MAX_FAILURES):
            failed = client.post(
                "/auth/login",
                json={"email": email, "password": "wrong-password"},
            )
            assert failed.status_code == 401

        blocked = client.post(
            "/auth/login",
            json={"email": email, "password": "correct-password"},
        )
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers


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

    def test_server_preserves_total_when_esp32_restarts(self, test_user, db_session):
        api_key = "device-key-reset-counter"
        device = Device(
            user_id=test_user.id,
            name="Medidor principal",
            api_key_hash=hash_api_key(api_key),
        )
        db_session.add(device)
        db_session.commit()
        headers = {"Authorization": f"Bearer {api_key}"}

        for event_id, raw_total in (
            ("RESET-TEST-EVENT-0001", 100.0),
            ("RESET-TEST-EVENT-0002", 105.0),
            ("RESET-TEST-EVENT-0003", 2.0),
        ):
            response = client.post(
                "/api/leitura",
                json={
                    "event_id": event_id,
                    "fluxo_litros": 1.0,
                    "consumo_total": raw_total,
                },
                headers=headers,
            )
            assert response.status_code == 200

        db_session.refresh(device)
        assert device.last_reported_total == 2.0
        assert device.calculated_consumption == 107.0
        readings = db_session.query(Leitura).order_by(Leitura.id).all()
        assert [reading.volume_delta for reading in readings] == [0.0, 5.0, 2.0]
        assert readings[-1].calculated_consumption == 107.0

    def test_zero_flow_clears_continuous_flow(self, test_user, db_session):
        api_key = "device-key-flow-state"
        device = Device(
            user_id=test_user.id,
            name="Medidor principal",
            api_key_hash=hash_api_key(api_key),
        )
        db_session.add(device)
        db_session.commit()
        headers = {"Authorization": f"Bearer {api_key}"}

        flowing = client.post(
            "/api/leitura",
            json={
                "event_id": "FLOW-STATE-EVENT-0001",
                "fluxo_litros": 1.0,
                "consumo_total": 10.0,
            },
            headers=headers,
        )
        assert flowing.status_code == 200
        db_session.refresh(device)
        assert device.continuous_flow_since is not None

        stopped = client.post(
            "/api/leitura",
            json={
                "event_id": "FLOW-STATE-EVENT-0002",
                "fluxo_litros": 0.0,
                "consumo_total": 10.0,
            },
            headers=headers,
        )
        assert stopped.status_code == 200
        db_session.refresh(device)
        assert device.continuous_flow_since is None


class TestDashboard:
    """Testes do dashboard"""

    def test_resumo_empty(self, test_user, auth_headers):
        """✓ Resumo com nenhuma leitura"""
        response = client.get("/dashboard/resumo", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["dispositivo"]["status"] == "nao_configurado"
        assert data["leituras_hoje"] == 0

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
        data = response.json()
        assert data["dispositivo"]["status"] == "online"
        assert data["leituras_hoje"] == 3
        assert data["dispositivo"]["situacao_agua"] == "fluxo_detectado"

    def test_resumo_marks_device_offline_after_timeout(
        self, test_user, db_session, auth_headers
    ):
        device = Device(
            user_id=test_user.id,
            name="Medidor externo",
            api_key_hash=hash_api_key("offline-device-key"),
            last_seen_at=utc_now() - timedelta(seconds=46),
        )
        db_session.add(device)
        db_session.commit()

        response = client.get("/dashboard/resumo", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["dispositivo"]["nome"] == "Medidor externo"
        assert data["dispositivo"]["status"] == "offline"
        assert data["dispositivo"]["segundos_desde_comunicacao"] >= 46
        assert data["dispositivo"]["situacao_agua"] == "sem_dados"

    def test_resumo_warns_about_continuous_flow(
        self, test_user, db_session, auth_headers
    ):
        now = utc_now()
        device = Device(
            user_id=test_user.id,
            name="Medidor externo",
            api_key_hash=hash_api_key("leak-device-key"),
            last_seen_at=now,
            continuous_flow_since=now - timedelta(minutes=31),
            last_reported_total=20.0,
            calculated_consumption=20.0,
        )
        db_session.add(device)
        db_session.flush()
        db_session.add(
            Leitura(
                user_id=test_user.id,
                device_id=device.id,
                fluxo_litros=0.5,
                consumo_total=20.0,
                calculated_consumption=20.0,
                timestamp=now,
            )
        )
        db_session.commit()

        response = client.get("/dashboard/resumo", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["dispositivo"]["possivel_vazamento"] is True
        assert data["dispositivo"]["fluxo_continuo_minutos"] >= 31

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

    def test_analytics_aggregates_and_compares_periods(
        self, test_user, db_session, auth_headers
    ):
        now = utc_now()
        db_session.add_all(
            [
                Leitura(
                    user_id=test_user.id,
                    fluxo_litros=1,
                    consumo_total=10,
                    volume_delta=1,
                    timestamp=now,
                ),
                Leitura(
                    user_id=test_user.id,
                    fluxo_litros=1,
                    consumo_total=12,
                    volume_delta=2,
                    timestamp=now,
                ),
                Leitura(
                    user_id=test_user.id,
                    fluxo_litros=1,
                    consumo_total=7,
                    volume_delta=2,
                    timestamp=now - timedelta(days=8),
                ),
            ]
        )
        db_session.commit()

        response = client.get("/dashboard/analise?dias=7", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["daily"]) == 7
        assert data["current_consumption"] == 3
        assert data["previous_consumption"] == 2
        assert data["variation_percent"] == 50


class TestDevices:
    def test_create_list_rename_disable_and_rotate_key(
        self, test_user, db_session, auth_headers
    ):
        created = client.post(
            "/devices",
            json={"name": "Caixa d'água"},
            headers=auth_headers,
        )
        assert created.status_code == 201
        created_data = created.json()
        device_id = created_data["device_id"]
        first_key = created_data["api_key"]

        listed = client.get("/devices", headers=auth_headers)
        assert listed.status_code == 200
        assert listed.json()[0]["name"] == "Caixa d'água"

        renamed = client.patch(
            f"/devices/{device_id}",
            json={"name": "Entrada principal"},
            headers=auth_headers,
        )
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Entrada principal"

        rotated = client.post(f"/devices/{device_id}/api-key", headers=auth_headers)
        assert rotated.status_code == 200
        assert rotated.json()["api_key"] != first_key

        disabled = client.patch(
            f"/devices/{device_id}",
            json={"is_active": False},
            headers=auth_headers,
        )
        assert disabled.status_code == 200
        assert disabled.json()["is_active"] is False

    def test_user_cannot_manage_another_users_device(
        self, test_user, db_session, auth_headers
    ):
        from auth_utils import hash_password
        from models import User

        other_user = User(
            email="other@example.com",
            password_hash=hash_password("password123"),
            is_active=True,
        )
        db_session.add(other_user)
        db_session.flush()
        device = Device(
            user_id=other_user.id,
            name="Medidor privado",
            api_key_hash=hash_api_key("other-users-key"),
        )
        db_session.add(device)
        db_session.commit()

        response = client.patch(
            f"/devices/{device.id}",
            json={"name": "Tentativa"},
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestSettings:
    def test_user_updates_goal_and_water_price(self, test_user, auth_headers):
        updated = client.patch(
            "/settings",
            json={"monthly_goal_liters": 12000, "water_price_per_m3": 8.5},
            headers=auth_headers,
        )
        assert updated.status_code == 200
        assert updated.json()["monthly_goal_liters"] == 12000
        assert updated.json()["water_price_per_m3"] == 8.5

        loaded = client.get("/settings", headers=auth_headers)
        assert loaded.status_code == 200
        assert loaded.json() == updated.json()


def test_dashboard_web_is_available():
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Cada litro conta" in response.text
    assert 'id="device-status"' in response.text
    assert 'id="device-last-seen"' in response.text


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
