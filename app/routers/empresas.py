from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.crud import empresa as crud_empresa
from app.dependency import get_db, get_empresa_actual
from app.exceptions import SinPermiso
from app.models.empresa import Empresa
from app.schemas.comun import IdPath
from app.schemas.empresa import (
    EmpresaCreate,
    EmpresaPatch,
    EmpresaRead,
    EmpresaUpdate,
)

router = APIRouter(prefix="/empresas", tags=["empresas"])


def _verificar_propia(empresa_id: int, empresa_actual: Empresa) -> None:
    """Una empresa solo puede ver, modificar o eliminar sus propios datos."""
    if empresa_id != empresa_actual.id:
        raise SinPermiso()


@router.post("/", response_model=EmpresaRead, status_code=201)
def crear_empresa(datos: EmpresaCreate, db: Session = Depends(get_db)):
    return crud_empresa.crear(db, datos)


# No hay listado de empresas: exponía el "usuario" (nombre de login) de todas,
# lo que permitía bloquear cuentas o probar contraseñas comunes en todas.


@router.get("/{empresa_id}", response_model=EmpresaRead)
def obtener_empresa(
    empresa_id: IdPath, empresa_actual: Empresa = Depends(get_empresa_actual)
):
    _verificar_propia(empresa_id, empresa_actual)
    return empresa_actual


@router.put("/{empresa_id}", response_model=EmpresaRead)
def actualizar_empresa(
    empresa_id: IdPath,
    datos: EmpresaUpdate,
    db: Session = Depends(get_db),
    empresa_actual: Empresa = Depends(get_empresa_actual),
):
    _verificar_propia(empresa_id, empresa_actual)
    empresa = crud_empresa.actualizar(db, empresa_id, datos)
    if empresa is None:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return empresa


@router.patch("/{empresa_id}", response_model=EmpresaRead)
def actualizar_empresa_parcial(
    empresa_id: IdPath,
    datos: EmpresaPatch,
    db: Session = Depends(get_db),
    empresa_actual: Empresa = Depends(get_empresa_actual),
):
    _verificar_propia(empresa_id, empresa_actual)
    empresa = crud_empresa.actualizar_parcial(db, empresa_id, datos)
    if empresa is None:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return empresa


@router.delete("/{empresa_id}", status_code=204)
def eliminar_empresa(
    empresa_id: IdPath,
    db: Session = Depends(get_db),
    empresa_actual: Empresa = Depends(get_empresa_actual),
):
    _verificar_propia(empresa_id, empresa_actual)
    if not crud_empresa.eliminar(db, empresa_id):
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
