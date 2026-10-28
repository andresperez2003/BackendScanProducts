from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.comun import Id


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    unit: str = Field(min_length=1, max_length=30)
    supplier_id: Id


class ProductCreate(ProductBase):
    pass


class ProductUpdate(ProductBase):
    pass


class ProductPatch(BaseModel):
    """Solo se modifican los campos enviados; null se rechaza con 422."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    supplier_id: Id | None = None

    @model_validator(mode="after")
    def _sin_null(self):
        for campo in self.model_fields_set:
            if getattr(self, campo) is None:
                raise ValueError(f"'{campo}' no puede ser null")
        return self


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # Solo lectura: no está en ProductCreate/Update, así que el cliente no puede cambiarlos.
    created_at: datetime
