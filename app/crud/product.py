from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud import supplier as crud_supplier
from app.exceptions import ProductoConSeguimientos, ProductoNoEncontrado, ProveedorNoEncontrado
from app.models.product import Product
from app.models.tracking import Tracking
from app.schemas.product import ProductCreate, ProductPatch, ProductUpdate


def crear(db: Session, empresa_id: int, datos: ProductCreate) -> Product:
    # El proveedor tiene que ser de la misma empresa
    crud_supplier.obtener(db, empresa_id, datos.supplier_id)
    product = Product(**datos.model_dump(), empresa_id=empresa_id)
    db.add(product)
    _guardar(db)
    db.refresh(product)
    return product


def listar(db: Session, empresa_id: int, supplier_id: int | None = None) -> list[Product]:
    consulta = select(Product).where(Product.empresa_id == empresa_id)
    if supplier_id is not None:
        consulta = consulta.where(Product.supplier_id == supplier_id)
    return list(db.scalars(consulta.order_by(Product.id)))


def obtener(db: Session, empresa_id: int, product_id: int) -> Product:
    """Devuelve el producto si es de la empresa; si no, ProductoNoEncontrado."""
    product = db.scalar(
        select(Product).where(Product.id == product_id, Product.empresa_id == empresa_id)
    )
    if product is None:
        raise ProductoNoEncontrado()
    return product


def actualizar(db: Session, empresa_id: int, product_id: int, datos: ProductUpdate) -> Product:
    return _aplicar_cambios(db, empresa_id, product_id, datos.model_dump())


def actualizar_parcial(
    db: Session, empresa_id: int, product_id: int, datos: ProductPatch
) -> Product:
    return _aplicar_cambios(db, empresa_id, product_id, datos.model_dump(exclude_unset=True))


def _aplicar_cambios(db: Session, empresa_id: int, product_id: int, cambios: dict) -> Product:
    product = obtener(db, empresa_id, product_id)
    if "supplier_id" in cambios:
        crud_supplier.obtener(db, empresa_id, cambios["supplier_id"])
    for campo, valor in cambios.items():
        setattr(product, campo, valor)
    _guardar(db)
    db.refresh(product)
    return product


def _guardar(db: Session) -> None:
    """Commit que traduce el error de clave foránea a 404.

    El proveedor se valida antes, pero otra petición puede eliminarlo justo
    entre esa validación y el commit; sin esto la API respondería 500.
    """
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ProveedorNoEncontrado() from None


def eliminar(db: Session, empresa_id: int, product_id: int) -> None:
    product = obtener(db, empresa_id, product_id)
    if _tiene_seguimientos(db, product.id):
        raise ProductoConSeguimientos()
    db.delete(product)
    try:
        db.commit()
    except IntegrityError:
        # Otra petición creó un seguimiento entre la verificación y el commit:
        # la clave foránea lo impide y se responde igual que arriba.
        db.rollback()
        raise ProductoConSeguimientos() from None


def _tiene_seguimientos(db: Session, product_id: int) -> bool:
    primero = db.scalar(select(Tracking.id).where(Tracking.product_id == product_id).limit(1))
    return primero is not None
