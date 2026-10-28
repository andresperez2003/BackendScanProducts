from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.crud import product as crud_product
from app.dependency import get_db, get_empresa_actual
from app.models.empresa import Empresa
from app.schemas.comun import IdPath, IdQuery
from app.schemas.product import (
    ProductCreate,
    ProductPatch,
    ProductRead,
    ProductUpdate,
)

router = APIRouter(prefix="/products", tags=["products"])


@router.post("/", response_model=ProductRead, status_code=201)
def crear_product(
    datos: ProductCreate,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    return crud_product.crear(db, empresa.id, datos)


@router.get("/", response_model=list[ProductRead])
def listar_products(
    supplier_id: IdQuery = None,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    """Lista los productos de la empresa; `?supplier_id=` filtra por proveedor."""
    return crud_product.listar(db, empresa.id, supplier_id)


@router.get("/{product_id}", response_model=ProductRead)
def obtener_product(
    product_id: IdPath,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    return crud_product.obtener(db, empresa.id, product_id)


@router.put("/{product_id}", response_model=ProductRead)
def actualizar_product(
    product_id: IdPath,
    datos: ProductUpdate,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    return crud_product.actualizar(db, empresa.id, product_id, datos)


@router.patch("/{product_id}", response_model=ProductRead)
def actualizar_product_parcial(
    product_id: IdPath,
    datos: ProductPatch,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    return crud_product.actualizar_parcial(db, empresa.id, product_id, datos)


@router.delete("/{product_id}", status_code=204)
def eliminar_product(
    product_id: IdPath,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    crud_product.eliminar(db, empresa.id, product_id)
