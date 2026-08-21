from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Boolean,
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
    created_at = Column(DateTime, default=utc_now)

    # Relacionamento
    leituras = relationship(
        "Leitura", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User(email='{self.email}')>"


class Leitura(Base):
    """Leitura de vazão do sensor"""

    __tablename__ = "leituras"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    fluxo_litros = Column(Float, nullable=False)  # Vazão instantânea em L/min
    consumo_total = Column(Float, nullable=False)  # Consumo acumulado em L
    timestamp = Column(DateTime, default=utc_now, index=True)

    # Relacionamento
    user = relationship("User", back_populates="leituras")

    def __repr__(self):
        return (
            f"<Leitura(fluxo={self.fluxo_litros}, consumo={self.consumo_total}, "
            f"ts={self.timestamp})>"
        )
