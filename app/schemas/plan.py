from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Soporte(BaseModel):
    """Contacto del equipo para adquirir un plan; None si no está configurado."""

    whatsapp: str | None
    correo: str | None


class PlanRead(BaseModel):
    """Plan de la empresa y cuántas lecturas de fotos lleva en el periodo actual."""

    # None = la empresa no tiene plan.
    plan_id: int | None
    nombre: str | None
    es_demo: bool
    lecturas_limite: int
    lecturas_usadas: int
    lecturas_restantes: int
    plan_desde: datetime | None
    plan_hasta: datetime | None
    vencido: bool
    # Por qué ya no puede leer fotos y el mensaje para el usuario; None si puede.
    motivo: Literal["sin_plan", "vencido", "agotado"] | None = None
    mensaje: str | None = None
    soporte: Soporte


class PlanDisponible(BaseModel):
    """Un plan que la empresa puede adquirir (lo que ve en "Mi plan")."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    precio: int  # pesos por periodo
    lecturas: int  # por periodo
    dias: int | None  # duración del periodo; None = no vence
