from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.crud import empresa as crud_empresa
from app.crud import plan as crud_plan
from app.dependency import get_db, get_empresa_actual
from app.models.empresa import Empresa
from app.schemas.auth import Token
from app.schemas.empresa import CambioContrasena, EmpresaRead
from app.schemas.plan import PlanDisponible, PlanRead
from app.security import crear_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    empresa = crud_empresa.autenticar(db, form.username, form.password)
    return Token(access_token=crear_token(empresa.id, empresa.version_token))


@router.get("/me", response_model=EmpresaRead)
def empresa_actual(empresa: Empresa = Depends(get_empresa_actual)):
    return empresa


@router.get("/plan", response_model=PlanRead)
def plan_actual(db: Session = Depends(get_db), empresa: Empresa = Depends(get_empresa_actual)):
    """Plan de la empresa y lecturas de fotos usadas y restantes en el periodo actual."""
    return crud_plan.estado(db, empresa)


@router.get("/planes", response_model=list[PlanDisponible], dependencies=[Depends(get_empresa_actual)])
def planes_disponibles(db: Session = Depends(get_db)):
    """Planes que la empresa puede adquirir (activos, sin la demo), del más barato al más caro.

    Se adquieren comunicándose con soporte (ver `soporte` en GET /auth/plan).
    """
    return crud_plan.disponibles(db)


@router.post("/cambiar-contrasena", response_model=Token)
def cambiar_contrasena(
    datos: CambioContrasena,
    db: Session = Depends(get_db),
    empresa: Empresa = Depends(get_empresa_actual),
):
    """Cambia la contraseña e invalida todos los tokens anteriores.

    Devuelve un token nuevo para que quien la cambió siga con la sesión abierta.
    """
    crud_empresa.cambiar_contrasena(
        db, empresa, datos.contrasena_actual, datos.contrasena_nueva
    )
    return Token(access_token=crear_token(empresa.id, empresa.version_token))
