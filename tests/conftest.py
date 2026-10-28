import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base
from app.dependency import get_db
from app.main import app
from app.models.plan import Plan
from app.security import crear_token

TEST_DB = "scanproducts_test"


def _url(nombre_db: str) -> str:
    settings = get_settings().model_copy(update={"postgres_db": nombre_db})
    return settings.database_url


@pytest.fixture(scope="session")
def engine():
    """Crea la base de testing (si no existe) y sus tablas, una vez por sesión."""
    admin = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        existe = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB}
        )
        if not existe:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    admin.dispose()

    engine = create_engine(_url(TEST_DB))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    # Los mismos planes que crea la migración; quedan fijos para todos los tests.
    with Session(engine) as session:
        session.add_all(
            [
                Plan(nombre="Demo", precio=0, lecturas=10, dias=None, es_demo=True),
                Plan(nombre="Básico", precio=15_000, lecturas=500, dias=30),
                Plan(nombre="Pro", precio=28_000, lecturas=1_000, dias=30),
            ]
        )
        session.commit()
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    """Sesión dentro de una transacción que se deshace al terminar cada test.

    Los commit/rollback del CRUD se convierten en savepoints, así que nada
    llega a guardarse de verdad.
    """
    conn = engine.connect()
    transaccion = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaccion.rollback()
    conn.close()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def planes(db) -> dict[str, Plan]:
    """Los planes iniciales por clave: "demo", "basico" y "pro"."""
    por_nombre = {plan.nombre: plan for plan in db.scalars(select(Plan))}
    return {"demo": por_nombre["Demo"], "basico": por_nombre["Básico"], "pro": por_nombre["Pro"]}


def headers_de(empresa_id: int, version_token: int = 0) -> dict[str, str]:
    """Headers con un token válido para la empresa indicada.

    Una empresa recién creada tiene version_token 0.
    """
    return {"Authorization": f"Bearer {crear_token(empresa_id, version_token)}"}


@pytest.fixture
def empresa_existente(client):
    respuesta = client.post(
        "/empresas/",
        json={"nombre": "Empresa Uno", "usuario": "empresa_uno", "contrasena": "secreta123"},
    )
    assert respuesta.status_code == 201
    return respuesta.json()


@pytest.fixture
def headers_auth(empresa_existente):
    return headers_de(empresa_existente["id"])


@pytest.fixture
def headers_otra_empresa(client):
    """Token de una segunda empresa, para probar que no ve datos ajenos."""
    respuesta = client.post(
        "/empresas/",
        json={"nombre": "Empresa Ajena", "usuario": "empresa_ajena", "contrasena": "clave1234"},
    )
    assert respuesta.status_code == 201
    return headers_de(respuesta.json()["id"])


@pytest.fixture
def supplier(client, headers_auth):
    respuesta = client.post("/suppliers/", json={"name": "Proveedor Uno"}, headers=headers_auth)
    assert respuesta.status_code == 201
    return respuesta.json()


@pytest.fixture
def product(client, headers_auth, supplier):
    respuesta = client.post(
        "/products/",
        json={"name": "Leche", "unit": "l", "supplier_id": supplier["id"]},
        headers=headers_auth,
    )
    assert respuesta.status_code == 201
    return respuesta.json()


@pytest.fixture
def tracking(client, headers_auth, product):
    respuesta = client.post(
        "/trackings/",
        json={"batch": "L-001", "due_date": "2026-12-31", "product_id": product["id"]},
        headers=headers_auth,
    )
    assert respuesta.status_code == 201
    return respuesta.json()
