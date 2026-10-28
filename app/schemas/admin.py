from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.comun import Id
from app.schemas.plan import PlanRead

# En intentos_login se guarda "admin:<usuario>" (máximo 50): 6 de prefijo.
ADMIN_USUARIO_MAX = 44


class AdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    usuario: str


# ---------------------------------------------------------------- planes

NombrePlan = Annotated[str, Field(min_length=1, max_length=50)]


class PlanAdminBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    nombre: NombrePlan
    precio: int = Field(ge=0, le=1_000_000_000)  # pesos por periodo
    lecturas: int = Field(ge=0, le=1_000_000)  # por periodo; en la demo, en total
    dias: int | None = Field(default=None, ge=1, le=3650)  # None = no vence
    activo: bool = True


class PlanCreate(PlanAdminBase):
    # forbid: "es_demo" no se puede mandar; solo existe el plan demo de la migración.
    model_config = ConfigDict(extra="forbid")


class PlanUpdate(PlanAdminBase):
    model_config = ConfigDict(extra="forbid")


class PlanAdminRead(PlanAdminBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    es_demo: bool
    # Cuántas empresas lo tienen asignado ahora.
    empresas: int = 0


# ---------------------------------------------------------------- empresas


class EmpresaAdminRead(BaseModel):
    """Una empresa vista por el administrador: sus datos y su plan con el consumo."""

    id: int
    nombre: str
    usuario: str
    plan: PlanRead


class AsignarPlan(BaseModel):
    """Plan que se activa desde ahora (el contador vuelve a 0); null = sin plan."""

    model_config = ConfigDict(extra="forbid")

    plan_id: Id | None


class ConsumoDia(BaseModel):
    fecha: date
    lecturas: int


class ConsumoRead(BaseModel):
    """Lecturas exitosas de una empresa por día (UTC), en los últimos `dias` días."""

    empresa_id: int
    desde: datetime
    total: int
    por_dia: list[ConsumoDia]
