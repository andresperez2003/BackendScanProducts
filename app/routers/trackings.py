from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.crud import plan as crud_plan
from app.crud import tracking as crud_tracking
from app.dependency import get_db, get_empresa_actual
from app.models.empresa import Empresa
from app.schemas.comun import IdPath, IdQuery
from app.services.extraccion import extraer_datos
from app.services.fotos import validar_foto
from app.schemas.tracking import (
    FotoRecibida,
    TrackingCreate,
    TrackingPatch,
    TrackingRead,
    TrackingUpdate,
)

router = APIRouter(prefix="/trackings", tags=["trackings"])


@router.post("/", response_model=TrackingRead, status_code=201)
def crear_tracking(
    datos: TrackingCreate,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    return crud_tracking.crear(db, empresa.id, datos)


@router.post("/photo", response_model=FotoRecibida)
async def recibir_foto(
    foto: UploadFile = File(...),
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    """Lee lote y vencimiento en la foto de un empaque (multipart/form-data, campo `foto`).

    Devuelve lo que leyó el modelo, con su confianza y notas, para que el
    frontend llene el formulario; **no crea el seguimiento** ni guarda la foto.
    Cada lectura exitosa cuenta para el plan de la empresa (ver GET /auth/plan).
    403 si no le quedan lecturas o el plan venció; 503 si falta
    OPENROUTER_API_KEY; 502 si la lectura falla (esas dos no cuentan).
    """
    tipo, contenido = await validar_foto(foto)
    # La base es síncrona: en un hilo aparte para no frenar las demás peticiones.
    lectura_id, restantes = await run_in_threadpool(crud_plan.reservar_lectura, db, empresa.id)
    try:
        extraccion = await extraer_datos(contenido, tipo)
    except Exception:
        await run_in_threadpool(crud_plan.liberar_lectura, db, lectura_id)
        raise
    return FotoRecibida(
        nombre=foto.filename,
        tipo=tipo,
        tamano_bytes=len(contenido),
        extraccion=extraccion,
        lecturas_restantes=restantes,
    )


@router.get("/", response_model=list[TrackingRead])
def listar_trackings(
    product_id: IdQuery = None,
    supplier_id: IdQuery = None,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    """Seguimientos de la empresa, del que vence antes al que vence después.

    `?product_id=` filtra por producto y `?supplier_id=` por proveedor.
    """
    return crud_tracking.listar(db, empresa.id, product_id, supplier_id)


@router.get("/{tracking_id}", response_model=TrackingRead)
def obtener_tracking(
    tracking_id: IdPath,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    return crud_tracking.obtener(db, empresa.id, tracking_id)


@router.put("/{tracking_id}", response_model=TrackingRead)
def actualizar_tracking(
    tracking_id: IdPath,
    datos: TrackingUpdate,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    return crud_tracking.actualizar(db, empresa.id, tracking_id, datos)


@router.patch("/{tracking_id}", response_model=TrackingRead)
def actualizar_tracking_parcial(
    tracking_id: IdPath,
    datos: TrackingPatch,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    return crud_tracking.actualizar_parcial(db, empresa.id, tracking_id, datos)


@router.delete("/{tracking_id}", status_code=204)
def eliminar_tracking(
    tracking_id: IdPath,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    crud_tracking.eliminar(db, empresa.id, tracking_id)
