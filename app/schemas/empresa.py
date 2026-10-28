from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

USUARIO_MAX = 50
CONTRASENA_MIN = 8
# Límite para que nadie mande contraseñas enormes y fuerce hashes lentos.
CONTRASENA_MAX = 128

Nombre = Annotated[str, Field(min_length=1, max_length=100)]
Usuario = Annotated[str, Field(min_length=1, max_length=USUARIO_MAX)]
Contrasena = Annotated[str, Field(min_length=CONTRASENA_MIN, max_length=CONTRASENA_MAX)]


class EmpresaBase(BaseModel):
    nombre: Nombre
    usuario: Usuario


class EmpresaCreate(EmpresaBase):
    contrasena: Contrasena


class EmpresaUpdate(EmpresaBase):
    # forbid: si alguien manda "contrasena" recibe 422 en vez de que se
    # ignore en silencio. La contraseña solo se cambia en /auth/cambiar-contrasena.
    model_config = ConfigDict(extra="forbid")


class EmpresaPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Nombre | None = None
    usuario: Usuario | None = None


class CambioContrasena(BaseModel):
    contrasena_actual: str = Field(max_length=CONTRASENA_MAX)
    contrasena_nueva: Contrasena


class EmpresaRead(EmpresaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
