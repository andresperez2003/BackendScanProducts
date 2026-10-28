from psycopg.errors import UniqueViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud import product as crud_product
from app.exceptions import LoteDuplicado, ProductoNoEncontrado, SeguimientoNoEncontrado
from app.models.product import Product
from app.models.tracking import Tracking
from app.schemas.tracking import TrackingCreate, TrackingPatch, TrackingUpdate


def crear(db: Session, empresa_id: int, datos: TrackingCreate) -> Tracking:
    # El producto tiene que ser de la misma empresa
    crud_product.obtener(db, empresa_id, datos.product_id)
    tracking = Tracking(**datos.model_dump(), empresa_id=empresa_id)
    db.add(tracking)
    _guardar(db, datos.batch)
    db.refresh(tracking)
    return tracking


def listar(
    db: Session,
    empresa_id: int,
    product_id: int | None = None,
    supplier_id: int | None = None,
) -> list[Tracking]:
    """Ordenados por vencimiento: los que vencen antes primero, sin fecha al final."""
    consulta = select(Tracking).where(Tracking.empresa_id == empresa_id)
    if product_id is not None:
        consulta = consulta.where(Tracking.product_id == product_id)
    if supplier_id is not None:
        consulta = consulta.where(
            Tracking.product_id.in_(select(Product.id).where(Product.supplier_id == supplier_id))
        )
    consulta = consulta.order_by(Tracking.due_date.asc().nulls_last(), Tracking.id)
    return list(db.scalars(consulta))


def obtener(db: Session, empresa_id: int, tracking_id: int) -> Tracking:
    """Devuelve el seguimiento si es de la empresa; si no, SeguimientoNoEncontrado."""
    tracking = db.scalar(
        select(Tracking).where(Tracking.id == tracking_id, Tracking.empresa_id == empresa_id)
    )
    if tracking is None:
        raise SeguimientoNoEncontrado()
    return tracking


def actualizar(
    db: Session, empresa_id: int, tracking_id: int, datos: TrackingUpdate
) -> Tracking:
    return _aplicar_cambios(db, empresa_id, tracking_id, datos.model_dump())


def actualizar_parcial(
    db: Session, empresa_id: int, tracking_id: int, datos: TrackingPatch
) -> Tracking:
    # Sin exclude_none: null en due_date significa "borrar la fecha"
    return _aplicar_cambios(db, empresa_id, tracking_id, datos.model_dump(exclude_unset=True))


def _aplicar_cambios(db: Session, empresa_id: int, tracking_id: int, cambios: dict) -> Tracking:
    tracking = obtener(db, empresa_id, tracking_id)
    if "product_id" in cambios:
        crud_product.obtener(db, empresa_id, cambios["product_id"])
    for campo, valor in cambios.items():
        setattr(tracking, campo, valor)
    batch = tracking.batch
    _guardar(db, batch)
    db.refresh(tracking)
    return tracking


def _guardar(db: Session, batch: str) -> None:
    """Commit que traduce los errores de integridad a respuestas claras.

    - Lote repetido para el mismo producto → 409.
    - El producto se eliminó entre la validación y el commit → 404.
    """
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if isinstance(error.orig, UniqueViolation):
            raise LoteDuplicado(batch) from None
        raise ProductoNoEncontrado() from None


def eliminar(db: Session, empresa_id: int, tracking_id: int) -> None:
    tracking = obtener(db, empresa_id, tracking_id)
    db.delete(tracking)
    db.commit()
