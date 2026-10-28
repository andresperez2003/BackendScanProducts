"""Administradores de la plataforma: login, contraseña y lo que ven del resto.

El login comparte el bloqueo por intentos fallidos de las empresas, con la
clave "admin:<usuario>" para que un administrador y una empresa con el mismo
usuario no se bloqueen entre sí.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Date, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.crud import intento_login as crud_intentos
from app.crud import plan as crud_plan
from app.exceptions import (
    ContrasenaActualIncorrecta,
    CredencialesInvalidas,
    EmpresaNoEncontrada,
    PlanDuplicado,
    PlanInactivo,
    PlanNoEncontrado,
    UsuarioYaExiste,
)
from app.models.administrador import Administrador
from app.models.empresa import Empresa
from app.models.lectura_foto import LecturaFoto
from app.models.plan import Plan
from app.schemas.admin import (
    ADMIN_USUARIO_MAX,
    ConsumoDia,
    ConsumoRead,
    EmpresaAdminRead,
    PlanAdminRead,
    PlanCreate,
    PlanUpdate,
)
from app.schemas.empresa import CONTRASENA_MAX
from app.security import hashear_contrasena, verificar_contrasena


def _clave_intentos(usuario: str) -> str:
    return f"admin:{usuario}"


# ---------------------------------------------------------------- administradores


def crear(db: Session, nombre: str, usuario: str, contrasena: str) -> Administrador:
    admin = Administrador(nombre=nombre, usuario=usuario, contrasena=hashear_contrasena(contrasena))
    db.add(admin)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise UsuarioYaExiste(usuario) from None
    db.refresh(admin)
    return admin


def obtener(db: Session, admin_id: int) -> Administrador | None:
    return db.get(Administrador, admin_id)


def autenticar(db: Session, usuario: str, contrasena: str) -> Administrador:
    if len(usuario) > ADMIN_USUARIO_MAX or len(contrasena) > CONTRASENA_MAX:
        raise CredencialesInvalidas()

    clave = _clave_intentos(usuario)
    crud_intentos.verificar_no_bloqueado(db, clave)
    admin = db.scalar(select(Administrador).where(Administrador.usuario == usuario))
    if not verificar_contrasena(contrasena, admin.contrasena if admin else None):
        crud_intentos.registrar_fallo(db, clave)
        raise CredencialesInvalidas()
    crud_intentos.limpiar(db, clave)
    return admin


def cambiar_contrasena(
    db: Session, admin: Administrador, contrasena_actual: str, contrasena_nueva: str
) -> None:
    clave = _clave_intentos(admin.usuario)
    crud_intentos.verificar_no_bloqueado(db, clave)
    if not verificar_contrasena(contrasena_actual, admin.contrasena):
        crud_intentos.registrar_fallo(db, clave)
        raise ContrasenaActualIncorrecta()
    crud_intentos.limpiar(db, clave)
    admin.contrasena = hashear_contrasena(contrasena_nueva)
    admin.version_token += 1
    db.commit()


# ---------------------------------------------------------------- empresas


def listar_empresas(db: Session, buscar: str | None = None) -> list[EmpresaAdminRead]:
    """Todas las empresas con su plan y consumo, por nombre. `buscar` filtra
    por nombre o usuario (sin importar mayúsculas)."""
    consulta = select(Empresa).options(joinedload(Empresa.plan)).order_by(func.lower(Empresa.nombre), Empresa.id)
    if buscar and buscar.strip():
        patron = f"%{_escapar_like(buscar.strip())}%"
        consulta = consulta.where(
            or_(Empresa.nombre.ilike(patron, escape="\\"), Empresa.usuario.ilike(patron, escape="\\"))
        )
    empresas = list(db.scalars(consulta))
    usadas = crud_plan.usadas_por_empresa(db, empresas)
    return [_empresa_admin(db, e, usadas.get(e.id, 0)) for e in empresas]


def obtener_empresa(db: Session, empresa_id: int) -> EmpresaAdminRead:
    return _empresa_admin(db, _empresa_o_404(db, empresa_id))


def asignar_plan(db: Session, empresa_id: int, plan_id: int | None) -> EmpresaAdminRead:
    """Activa el plan desde ahora (también sirve para renovar) o deja sin plan."""
    empresa = _empresa_o_404(db, empresa_id)
    plan = None
    if plan_id is not None:
        plan = _plan_o_404(db, plan_id)
        if not plan.activo:
            raise PlanInactivo(plan.nombre)
    crud_plan.activar(db, empresa, plan)
    return _empresa_admin(db, empresa)


def consumo(db: Session, empresa_id: int, dias: int) -> ConsumoRead:
    """Lecturas exitosas por día (UTC) en los últimos `dias` días, sin huecos."""
    _empresa_o_404(db, empresa_id)
    hoy = datetime.now(UTC).date()
    primer_dia = hoy - timedelta(days=dias - 1)
    desde = datetime.combine(primer_dia, datetime.min.time(), tzinfo=UTC)
    dia = cast(func.timezone("UTC", LecturaFoto.creada_en), Date)
    filas = db.execute(
        select(dia, func.count())
        .where(LecturaFoto.empresa_id == empresa_id, LecturaFoto.creada_en >= desde)
        .group_by(dia)
    )
    por_fecha: dict[date, int] = dict(filas.all())
    por_dia = [
        ConsumoDia(fecha=fecha, lecturas=por_fecha.get(fecha, 0))
        for fecha in (primer_dia + timedelta(days=i) for i in range(dias))
    ]
    return ConsumoRead(empresa_id=empresa_id, desde=desde, total=sum(por_fecha.values()), por_dia=por_dia)


def _empresa_admin(db: Session, empresa: Empresa, usadas: int | None = None) -> EmpresaAdminRead:
    return EmpresaAdminRead(
        id=empresa.id,
        nombre=empresa.nombre,
        usuario=empresa.usuario,
        plan=crud_plan.estado(db, empresa, usadas),
    )


def _empresa_o_404(db: Session, empresa_id: int) -> Empresa:
    empresa = db.get(Empresa, empresa_id)
    if empresa is None:
        raise EmpresaNoEncontrada()
    return empresa


def _escapar_like(texto: str) -> str:
    """Para que % y _ escritos en el buscador se busquen tal cual."""
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---------------------------------------------------------------- planes


def listar_planes(db: Session) -> list[PlanAdminRead]:
    cuantas = dict(
        db.execute(
            select(Empresa.plan_id, func.count()).where(Empresa.plan_id.is_not(None)).group_by(Empresa.plan_id)
        ).all()
    )
    return [_plan_admin(plan, cuantas.get(plan.id, 0)) for plan in crud_plan.listar(db)]


def crear_plan(db: Session, datos: PlanCreate) -> PlanAdminRead:
    _verificar_nombre_libre(db, datos.nombre)
    plan = Plan(**datos.model_dump())
    db.add(plan)
    _guardar_plan(db, datos.nombre)
    db.refresh(plan)
    return _plan_admin(plan, 0)


def actualizar_plan(db: Session, plan_id: int, datos: PlanUpdate) -> PlanAdminRead:
    """Los cambios aplican también al periodo en curso de las empresas que lo
    tienen (ej. más lecturas). Cambiar `dias` solo afecta las próximas activaciones."""
    plan = _plan_o_404(db, plan_id)
    _verificar_nombre_libre(db, datos.nombre, plan.id)
    for campo, valor in datos.model_dump().items():
        setattr(plan, campo, valor)
    _guardar_plan(db, datos.nombre)
    db.refresh(plan)
    cuantas = db.scalar(select(func.count()).select_from(Empresa).where(Empresa.plan_id == plan.id))
    return _plan_admin(plan, cuantas)


def _verificar_nombre_libre(db: Session, nombre: str, plan_id: int | None = None) -> None:
    """"Basico" y "Básico" cuentan como el mismo nombre: la consola los busca así."""
    otro = crud_plan.buscar(db, nombre)
    if otro is not None and otro.id != plan_id:
        raise PlanDuplicado(nombre)


def _guardar_plan(db: Session, nombre: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise PlanDuplicado(nombre) from None


def _plan_admin(plan: Plan, empresas: int) -> PlanAdminRead:
    return PlanAdminRead.model_validate(plan).model_copy(update={"empresas": empresas})


def _plan_o_404(db: Session, plan_id: int) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise PlanNoEncontrado()
    return plan
