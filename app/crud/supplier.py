from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exceptions import ProveedorConProductos, ProveedorNoEncontrado
from app.models.product import Product
from app.models.supplier import Supplier
from app.schemas.supplier import SupplierCreate, SupplierPatch, SupplierUpdate


def crear(db: Session, empresa_id: int, datos: SupplierCreate) -> Supplier:
    supplier = Supplier(**datos.model_dump(), empresa_id=empresa_id)
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def listar(db: Session, empresa_id: int) -> list[Supplier]:
    consulta = select(Supplier).where(Supplier.empresa_id == empresa_id).order_by(Supplier.id)
    return list(db.scalars(consulta))


def obtener(db: Session, empresa_id: int, supplier_id: int) -> Supplier:
    """Devuelve el proveedor si es de la empresa; si no, ProveedorNoEncontrado."""
    supplier = db.scalar(
        select(Supplier).where(Supplier.id == supplier_id, Supplier.empresa_id == empresa_id)
    )
    if supplier is None:
        raise ProveedorNoEncontrado()
    return supplier


def actualizar(
    db: Session, empresa_id: int, supplier_id: int, datos: SupplierUpdate
) -> Supplier:
    return _aplicar_cambios(db, empresa_id, supplier_id, datos.model_dump())


def actualizar_parcial(
    db: Session, empresa_id: int, supplier_id: int, datos: SupplierPatch
) -> Supplier:
    cambios = datos.model_dump(exclude_unset=True, exclude_none=True)
    return _aplicar_cambios(db, empresa_id, supplier_id, cambios)


def _aplicar_cambios(
    db: Session, empresa_id: int, supplier_id: int, cambios: dict
) -> Supplier:
    supplier = obtener(db, empresa_id, supplier_id)
    for campo, valor in cambios.items():
        setattr(supplier, campo, valor)
    db.commit()
    db.refresh(supplier)
    return supplier


def eliminar(db: Session, empresa_id: int, supplier_id: int) -> None:
    supplier = obtener(db, empresa_id, supplier_id)
    if _tiene_productos(db, supplier.id):
        raise ProveedorConProductos()
    db.delete(supplier)
    try:
        db.commit()
    except IntegrityError:
        # Otra petición creó un producto entre la verificación y el commit:
        # la clave foránea lo impide y se responde igual que arriba.
        db.rollback()
        raise ProveedorConProductos() from None


def _tiene_productos(db: Session, supplier_id: int) -> bool:
    primero = db.scalar(select(Product.id).where(Product.supplier_id == supplier_id).limit(1))
    return primero is not None
