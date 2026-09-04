from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from auth_utils import utc_now
from database import Base


class User(Base):
    """Usuário do sistema"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    api_key = Column(String, unique=True, index=True, nullable=True)
    api_key_expires_at = Column(DateTime, nullable=True)
    monthly_goal_liters = Column(Float, nullable=True)
    water_price_per_m3 = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    # Relacionamento
    leituras = relationship(
        "Leitura", back_populates="user", cascade="all, delete-orphan"
    )
    devices = relationship(
        "Device", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User(email='{self.email}')>"


class Device(Base):
    """Aparelho ESP32 autorizado a enviar leituras."""

    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(80), nullable=False, default="Meu medidor")
    api_key_hash = Column(String(64), unique=True, index=True, nullable=False)
    api_key_expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_seen_at = Column(DateTime, nullable=True)
    last_reported_total = Column(Float, nullable=True)
    calculated_consumption = Column(Float, default=0.0, nullable=False)
    continuous_flow_since = Column(DateTime, nullable=True)
    firmware_version = Column(String(32), nullable=True)
    wifi_rssi = Column(Integer, nullable=True)
    pending_queue = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    user = relationship("User", back_populates="devices")
    leituras = relationship("Leitura", back_populates="device")


class Leitura(Base):
    """Leitura de vazão do sensor"""

    __tablename__ = "leituras"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True, index=True)
    event_id = Column(String(96), nullable=True)
    fluxo_litros = Column(Float, nullable=False)  # Vazão instantânea em L/min
    consumo_total = Column(Float, nullable=False)  # Consumo acumulado em L
    volume_delta = Column(Float, default=0.0, nullable=False)
    calculated_consumption = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=utc_now, index=True)  # horário da medição
    received_at = Column(DateTime, default=utc_now, nullable=False)

    # Relacionamento
    user = relationship("User", back_populates="leituras")
    device = relationship("Device", back_populates="leituras")

    __table_args__ = (
        UniqueConstraint("device_id", "event_id", name="uq_device_event"),
    )

    def __repr__(self):
        return (
            f"<Leitura(fluxo={self.fluxo_litros}, consumo={self.consumo_total}, "
            f"ts={self.timestamp})>"
        )
