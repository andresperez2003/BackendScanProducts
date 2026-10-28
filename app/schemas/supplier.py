from pydantic import BaseModel, ConfigDict, Field


class SupplierBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(SupplierBase):
    pass


class SupplierPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)


class SupplierRead(SupplierBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
