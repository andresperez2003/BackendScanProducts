from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.comun import Id
from app.schemas.supplier import SupplierRead


class TrackingBase(BaseModel):
    batch: str = Field(min_length=1, max_length=50)
    due_date: date | None = None
    product_id: Id


class TrackingCreate(TrackingBase):
    pass


class TrackingUpdate(TrackingBase):
    pass


class TrackingPatch(BaseModel):
    """Solo se modifican los campos enviados.

    `due_date` acepta null para borrarla; en los campos obligatorios null no
    tiene sentido y se rechaza con 422.
    """

    batch: str | None = Field(default=None, min_length=1, max_length=50)
    due_date: date | None = None
    product_id: Id | None = None

    @model_validator(mode="after")
    def _sin_null_en_obligatorios(self):
        for campo in ("batch", "product_id"):
            if campo in self.model_fields_set and getattr(self, campo) is None:
                raise ValueError(f"'{campo}' no puede ser null")
        return self


class ProductoResumen(BaseModel):
    """Lo necesario del producto para mostrar un seguimiento."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    unit: str


class TrackingRead(TrackingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    # Solo lectura: vienen del producto, así el cliente no tiene que buscarlos aparte.
    product: ProductoResumen
    supplier: SupplierRead


class ExtraccionFoto(BaseModel):
    """Lo que el modelo leyó en la foto. Es una sugerencia para el formulario:
    el usuario la revisa antes de guardar el seguimiento."""

    lote: str | None
    # Fecha lista para el formulario (YYYY-MM-DD). Si el empaque solo trae mes
    # y año, es el último día de ese mes. None si no se leyó o no es válida.
    fecha_vencimiento: date | None
    fecha_cruda: str | None
    venc_precision: Literal["dia", "mes", "nulo"]
    confianza: Literal["alta", "media", "baja"]
    notas: str | None


class FotoRecibida(BaseModel):
    """La foto recibida (no se guarda) y lo que el modelo leyó en ella."""

    recibida: bool = True
    nombre: str | None
    tipo: str
    tamano_bytes: int
    extraccion: ExtraccionFoto
    # Lecturas que le quedan a la empresa en su plan, contando esta.
    lecturas_restantes: int
