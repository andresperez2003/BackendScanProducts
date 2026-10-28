"""Plan de cada empresa y el límite de lecturas de fotos.

Una lectura se reserva antes de llamar al modelo y se libera si falla: así
solo cuentan las exitosas, y dos fotos enviadas a la vez no pueden pasar
juntas el límite (la reserva bloquea la fila de la empresa).
"""

import unicodedata
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.exceptions import DemasiadasLecturas, SinLecturas
from app.models.empresa import Empresa
from app.models.lectura_foto import LecturaFoto
from app.models.plan import Plan
from app.schemas.plan import PlanRead, Soporte

VENTANA_RAFAGA = timedelta(minutes=1)


def soporte() -> Soporte:
    settings = get_settings()
    return Soporte(whatsapp=settings.soporte_whatsapp, correo=settings.soporte_correo)


def usadas_por_empresa(db: Session, empresas: list[Empresa]) -> dict[int, int]:
    """Lecturas del periodo actual de varias empresas en una sola consulta."""
    con_plan = [e for e in empresas if e.plan_desde is not None]
    if not con_plan:
        return {}
    desde = (
        select(Empresa.id, Empresa.plan_desde)
        .where(Empresa.id.in_([e.id for e in con_plan]))
        .subquery()
    )
    filas = db.execute(
        select(LecturaFoto.empresa_id, func.count())
        .join(desde, (desde.c.id == LecturaFoto.empresa_id) & (LecturaFoto.creada_en >= desde.c.plan_desde))
        .group_by(LecturaFoto.empresa_id)
    )
    return dict(filas.all())


def estado(db: Session, empresa: Empresa, usadas: int | None = None) -> PlanRead:
    """Plan y consumo de la empresa. `usadas` evita contarlas si ya se sabe."""
    plan = empresa.plan
    if plan is None:
        actual = PlanRead(
            plan_id=None,
            nombre=None,
            es_demo=False,
            lecturas_limite=0,
            lecturas_usadas=0,
            lecturas_restantes=0,
            plan_desde=None,
            plan_hasta=None,
            vencido=False,
            soporte=soporte(),
        )
    else:
        if usadas is None:
            usadas = db.scalar(
                select(func.count())
                .select_from(LecturaFoto)
                .where(LecturaFoto.empresa_id == empresa.id, LecturaFoto.creada_en >= empresa.plan_desde)
            )
        vencido = empresa.plan_hasta is not None and empresa.plan_hasta <= datetime.now(UTC)
        actual = PlanRead(
            plan_id=plan.id,
            nombre=plan.nombre,
            es_demo=plan.es_demo,
            lecturas_limite=plan.lecturas,
            lecturas_usadas=usadas,
            lecturas_restantes=0 if vencido else max(0, plan.lecturas - usadas),
            plan_desde=empresa.plan_desde,
            plan_hasta=empresa.plan_hasta,
            vencido=vencido,
            soporte=soporte(),
        )
    if actual.lecturas_restantes == 0:
        actual.motivo, actual.mensaje = _motivo(actual)
    return actual


def reservar_lectura(db: Session, empresa_id: int) -> tuple[int, int]:
    """Reserva una lectura. Devuelve (id de la reserva, lecturas que quedan después).

    Lanza SinLecturas si no tiene plan, el plan venció o ya no le quedan, y
    DemasiadasLecturas si superó las lecturas por minuto.
    """
    empresa = db.scalar(
        select(Empresa)
        .options(joinedload(Empresa.plan))
        .where(Empresa.id == empresa_id)
        # Solo la fila de la empresa: el plan puede faltar (LEFT JOIN).
        .with_for_update(of=Empresa)
        .execution_options(populate_existing=True)
    )
    actual = estado(db, empresa)
    if actual.lecturas_restantes <= 0:
        db.rollback()  # suelta el bloqueo
        raise SinLecturas(actual.mensaje, actual.motivo, actual.soporte.model_dump())
    _verificar_rafaga(db, empresa_id)
    lectura = LecturaFoto(empresa_id=empresa_id)
    db.add(lectura)
    db.commit()
    return lectura.id, actual.lecturas_restantes - 1


def _verificar_rafaga(db: Session, empresa_id: int) -> None:
    ahora = datetime.now(UTC)
    recientes = db.scalars(
        select(LecturaFoto.creada_en)
        .where(LecturaFoto.empresa_id == empresa_id, LecturaFoto.creada_en > ahora - VENTANA_RAFAGA)
        .order_by(LecturaFoto.creada_en)
    ).all()
    limite = get_settings().lecturas_por_minuto
    if len(recientes) >= limite:
        db.rollback()  # suelta el bloqueo
        # Se libera un cupo cuando la más vieja de las últimas `limite` sale de la ventana.
        raise DemasiadasLecturas(recientes[-limite] + VENTANA_RAFAGA - ahora)


def liberar_lectura(db: Session, lectura_id: int) -> None:
    """Devuelve una lectura reservada cuyo modelo falló: no cuenta."""
    db.execute(delete(LecturaFoto).where(LecturaFoto.id == lectura_id))
    db.commit()


def activar(db: Session, empresa: Empresa, plan: Plan | None) -> None:
    """Cambia el plan desde ahora: el contador de lecturas vuelve a cero.

    Sirve también para renovar: volver a activar el mismo plan empieza otro
    periodo. None deja a la empresa sin plan.
    """
    ahora = datetime.now(UTC)
    empresa.plan = plan
    empresa.plan_desde = ahora if plan else None
    empresa.plan_hasta = ahora + timedelta(days=plan.dias) if plan and plan.dias else None
    db.commit()


def asignar_demo(db: Session, empresa: Empresa) -> None:
    """Pone a una empresa nueva en el plan demo, si hay uno activo (sin commit)."""
    demo = db.scalar(select(Plan).where(Plan.es_demo, Plan.activo))
    if demo is not None:
        empresa.plan = demo
        empresa.plan_desde = datetime.now(UTC)


def listar(db: Session) -> list[Plan]:
    return list(db.scalars(select(Plan).order_by(Plan.precio, Plan.id)))


def buscar(db: Session, nombre: str) -> Plan | None:
    """Plan por nombre, sin importar mayúsculas ni tildes ("basico" → Básico)."""
    buscado = _normalizar(nombre)
    return next((plan for plan in listar(db) if _normalizar(plan.nombre) == buscado), None)


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.strip().lower()


def _motivo(actual: PlanRead) -> tuple[str, str]:
    if actual.plan_id is None:
        return "sin_plan", (
            "Tu cuenta no tiene un plan con lectura de fotos. "
            "Comunícate con el equipo de soporte para adquirir uno."
        )
    if actual.vencido:
        return "vencido", (
            f"Tu plan {actual.nombre} venció. Comunícate con el equipo de soporte para renovarlo."
        )
    if actual.es_demo:
        return "agotado", (
            # Con el nombre real: el plan demo se puede renombrar desde el panel.
            f"Ya usaste las {actual.lecturas_limite} lecturas de prueba de tu plan {actual.nombre}. "
            "Comunícate con el equipo de soporte para adquirir un plan."
        )
    return "agotado", (
        f"Ya usaste las {actual.lecturas_limite} lecturas de tu plan {actual.nombre} de este "
        "periodo. Comunícate con el equipo de soporte para renovarlo o adquirir un plan con más lecturas."
    )


def disponibles(db: Session) -> list[Plan]:
    """Planes que una empresa puede adquirir: los activos, sin la demo."""
    return list(db.scalars(select(Plan).where(Plan.activo, Plan.es_demo.is_(False)).order_by(Plan.precio, Plan.id)))
