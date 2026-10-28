"""Administración desde la consola: el primer administrador y los planes (respaldo del panel).

    python -m app.cli planes                    lista los planes
    python -m app.cli ver <usuario>             plan y lecturas usadas de la empresa
    python -m app.cli plan <usuario> <plan>     activa el plan desde hoy (por nombre: demo, basico, pro...)
    python -m app.cli quitar <usuario>          deja a la empresa sin plan
    python -m app.cli crear-admin <usuario>     crea un administrador del panel (pide la contraseña)

Con Docker: docker compose exec api python -m app.cli ver <usuario>

Activar un plan reinicia el contador de lecturas y, en los pagos, cuenta
sus días desde hoy. Para renovar se vuelve a activar el mismo plan.
"""

import argparse
import getpass
import sys

from app.crud import administrador as crud_admin
from app.crud import empresa as crud_empresa
from app.crud import plan as crud_plan
from app.database import SessionLocal
from app.exceptions import UsuarioYaExiste
from app.schemas.admin import ADMIN_USUARIO_MAX
from app.schemas.empresa import CONTRASENA_MAX, CONTRASENA_MIN


def _imprimir(db, empresa) -> None:
    estado = crud_plan.estado(db, empresa)
    print(f"{empresa.nombre} ({empresa.usuario})")
    if estado.plan_id is None:
        print("  Plan:     sin plan")
        return
    vence = f"{estado.plan_hasta:%Y-%m-%d %H:%M} UTC" if estado.plan_hasta else "no vence"
    print(f"  Plan:     {estado.nombre}{' (VENCIDO)' if estado.vencido else ''}")
    print(f"  Desde:    {estado.plan_desde:%Y-%m-%d %H:%M} UTC")
    print(f"  Vence:    {vence}")
    print(f"  Lecturas: {estado.lecturas_usadas} usadas de {estado.lecturas_limite}, quedan {estado.lecturas_restantes}")


def _listar_planes(db) -> None:
    for plan in crud_plan.listar(db):
        duracion = f"{plan.dias} días" if plan.dias else "no vence"
        marcas = [m for m, si in (("demo", plan.es_demo), ("inactivo", not plan.activo)) if si]
        extra = f"  [{', '.join(marcas)}]" if marcas else ""
        print(f"  {plan.nombre:<12} ${plan.precio:>8,}  {plan.lecturas:>6} lecturas  {duracion}{extra}")


def _pedir_contrasena() -> str | None:
    """Pide la contraseña dos veces sin mostrarla (no queda en el historial)."""
    contrasena = getpass.getpass("Contraseña: ")
    if not CONTRASENA_MIN <= len(contrasena) <= CONTRASENA_MAX:
        print(f"La contraseña debe tener entre {CONTRASENA_MIN} y {CONTRASENA_MAX} caracteres", file=sys.stderr)
        return None
    if getpass.getpass("Repite la contraseña: ") != contrasena:
        print("Las contraseñas no coinciden", file=sys.stderr)
        return None
    return contrasena


def _crear_admin(db, usuario: str, nombre: str | None) -> int:
    if not 1 <= len(usuario) <= ADMIN_USUARIO_MAX:
        print(f"El usuario debe tener entre 1 y {ADMIN_USUARIO_MAX} caracteres", file=sys.stderr)
        return 1
    contrasena = _pedir_contrasena()
    if contrasena is None:
        return 1
    try:
        crud_admin.crear(db, nombre or usuario, usuario, contrasena)
    except UsuarioYaExiste:
        print(f"Ya existe un administrador con el usuario '{usuario}'", file=sys.stderr)
        return 1
    print(f"Administrador '{usuario}' creado. Entra en el panel con ese usuario.")
    return 0


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Planes de las empresas")
    comandos = parser.add_subparsers(dest="comando", required=True)
    comandos.add_parser("planes", help="lista los planes")
    ver = comandos.add_parser("ver", help="muestra el plan de una empresa")
    ver.add_argument("usuario")
    plan = comandos.add_parser("plan", help="activa un plan desde hoy")
    plan.add_argument("usuario")
    plan.add_argument("plan")
    quitar = comandos.add_parser("quitar", help="deja a la empresa sin plan")
    quitar.add_argument("usuario")
    admin = comandos.add_parser("crear-admin", help="crea un administrador del panel")
    admin.add_argument("usuario")
    admin.add_argument("--nombre", help="nombre para mostrar (por defecto, el usuario)")
    args = parser.parse_args(argumentos)

    with SessionLocal() as db:
        if args.comando == "crear-admin":
            return _crear_admin(db, args.usuario, args.nombre)
        if args.comando == "planes":
            _listar_planes(db)
            return 0
        empresa = crud_empresa.obtener_por_usuario(db, args.usuario)
        if empresa is None:
            print(f"No existe una empresa con el usuario '{args.usuario}'", file=sys.stderr)
            return 1
        if args.comando == "plan":
            elegido = crud_plan.buscar(db, args.plan)
            if elegido is None:
                print(f"No existe el plan '{args.plan}'. Planes:", file=sys.stderr)
                _listar_planes(db)
                return 1
            crud_plan.activar(db, empresa, elegido)
            print("Plan activado.")
        elif args.comando == "quitar":
            crud_plan.activar(db, empresa, None)
            print("Plan quitado.")
        _imprimir(db, empresa)
    return 0


if __name__ == "__main__":
    sys.exit(main())
