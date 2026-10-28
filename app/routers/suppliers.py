from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.crud import supplier as crud_supplier
from app.dependency import get_db, get_empresa_actual
from app.models.empresa import Empresa
from app.schemas.comun import IdPath
from app.schemas.supplier import (
    SupplierCreate,
    SupplierPatch,
    SupplierRead,
    SupplierUpdate,
)

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.post("/", response_model=SupplierRead, status_code=201)
def crear_supplier(
    datos: SupplierCreate,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    return crud_supplier.crear(db, empresa.id, datos)


@router.get("/", response_model=list[SupplierRead])
def listar_suppliers(
    db: Session = Depends(get_db), empresa: Empresa = Depends(get_empresa_actual)
):
    return crud_supplier.listar(db, empresa.id)


@router.get("/{supplier_id}", response_model=SupplierRead)
def obtener_supplier(
    supplier_id: IdPath,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    return crud_supplier.obtener(db, empresa.id, supplier_id)


@router.put("/{supplier_id}", response_model=SupplierRead)
def actualizar_supplier(
    supplier_id: IdPath,
    datos: SupplierUpdate,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    return crud_supplier.actualizar(db, empresa.id, supplier_id, datos)


@router.patch("/{supplier_id}", response_model=SupplierRead)
def actualizar_supplier_parcial(
    supplier_id: IdPath,
    datos: SupplierPatch,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    return crud_supplier.actualizar_parcial(db, empresa.id, supplier_id, datos)


@router.delete("/{supplier_id}", status_code=204)
def eliminar_supplier(
    supplier_id: IdPath,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    crud_supplier.eliminar(db, empresa.id, supplier_id)
