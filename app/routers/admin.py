"""Panel del superadministrador: planes de las empresas y su consumo.

Todo exige un token de administrador (POST /admin/auth/login); el de una
empresa recibe 401. El primer administrador se crea por consola:
python -m app.cli crear-admin <usuario>
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.crud import administrador as crud_admin
from app.dependency import get_admin_actual, get_db
from app.models.administrador import Administrador
from app.schemas.admin import (
    AdminRead,
    AsignarPlan,
    ConsumoRead,
    EmpresaAdminRead,
    PlanAdminRead,
    PlanCreate,
    PlanUpdate,
)
from app.schemas.auth import Token
from app.schemas.comun import IdPath
from app.schemas.empresa import CambioContrasena
from app.security import crear_token

router = APIRouter(prefix="/admin", tags=["admin"])
# Todo lo de /admin salvo el login.
protegido = APIRouter(dependencies=[Depends(get_admin_actual)])


@router.post("/auth/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    admin = crud_admin.autenticar(db, form.username, form.password)
    return Token(access_token=crear_token(admin.id, admin.version_token, tipo="admin"))


@protegido.get("/auth/me", response_model=AdminRead)
def admin_actual(admin: Administrador = Depends(get_admin_actual)):
    return admin


@protegido.post("/auth/cambiar-contrasena", response_model=Token)
def cambiar_contrasena(
    datos: CambioContrasena,
    db: Session = Depends(get_db),
    admin: Administrador = Depends(get_admin_actual),
):
    """Cambia la contraseña e invalida los tokens anteriores; devuelve uno nuevo."""
    crud_admin.cambiar_contrasena(db, admin, datos.contrasena_actual, datos.contrasena_nueva)
    return Token(access_token=crear_token(admin.id, admin.version_token, tipo="admin"))


# ---------------------------------------------------------------- empresas


@protegido.get("/empresas", response_model=list[EmpresaAdminRead])
def listar_empresas(
    buscar: Annotated[str | None, Query(max_length=100)] = None,
    db: Session = Depends(get_db),
):
    """Empresas con su plan y consumo, por nombre. `?buscar=` filtra por nombre o usuario."""
    return crud_admin.listar_empresas(db, buscar)


@protegido.get("/empresas/{empresa_id}", response_model=EmpresaAdminRead)
def obtener_empresa(empresa_id: IdPath, db: Session = Depends(get_db)):
    return crud_admin.obtener_empresa(db, empresa_id)


@protegido.put("/empresas/{empresa_id}/plan", response_model=EmpresaAdminRead)
def asignar_plan(empresa_id: IdPath, datos: AsignarPlan, db: Session = Depends(get_db)):
    """Activa un plan desde ahora: el contador de lecturas vuelve a 0 y, si el
    plan tiene días, vence en esos días. Activar el mismo plan lo renueva.
    `plan_id: null` deja a la empresa sin plan. 409 si el plan está desactivado.
    """
    return crud_admin.asignar_plan(db, empresa_id, datos.plan_id)


@protegido.get("/empresas/{empresa_id}/consumo", response_model=ConsumoRead)
def consumo(
    empresa_id: IdPath,
    dias: Annotated[int, Query(ge=1, le=366)] = 30,
    db: Session = Depends(get_db),
):
    """Lecturas exitosas por día (UTC) en los últimos `dias` días."""
    return crud_admin.consumo(db, empresa_id, dias)


# ---------------------------------------------------------------- planes


@protegido.get("/planes", response_model=list[PlanAdminRead])
def listar_planes(db: Session = Depends(get_db)):
    """Todos los planes, activos o no, con cuántas empresas tiene cada uno."""
    return crud_admin.listar_planes(db)


@protegido.post("/planes", response_model=PlanAdminRead, status_code=201)
def crear_plan(datos: PlanCreate, db: Session = Depends(get_db)):
    return crud_admin.crear_plan(db, datos)


@protegido.put("/planes/{plan_id}", response_model=PlanAdminRead)
def actualizar_plan(plan_id: IdPath, datos: PlanUpdate, db: Session = Depends(get_db)):
    """Las lecturas nuevas aplican también al periodo en curso de quienes lo
    tienen; los días, desde la próxima activación. `activo: false` lo saca de
    la lista para asignar (las empresas que lo tienen lo conservan).
    No hay DELETE: un plan se desactiva."""
    return crud_admin.actualizar_plan(db, plan_id, datos)


router.include_router(protegido)
