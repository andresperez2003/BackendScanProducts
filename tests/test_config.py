import pytest
from pydantic import ValidationError

from app.config import Settings

NEON = "ep-ejemplo.us-east-1.aws.neon.tech/neondb?sslmode=require"


@pytest.fixture
def sin_entorno(monkeypatch):
    """Settings sin leer .env ni las variables del contenedor."""
    for nombre in ("DATABASE_URL", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "DB_HOST", "DB_PORT"):
        monkeypatch.delenv(nombre, raising=False)

    def crear(**valores):
        return Settings(_env_file=None, secret_key="x" * 40, **valores)

    return crear


def test_piezas_sueltas_como_en_local(sin_entorno):
    settings = sin_entorno(postgres_user="u", postgres_password="p", postgres_db="db", db_host="db")

    assert settings.database_url == "postgresql+psycopg://u:p@db:5432/db"


@pytest.mark.parametrize("prefijo", ["postgresql://", "postgres://", "postgresql+psycopg://"])
def test_database_url_agrega_el_driver(sin_entorno, monkeypatch, prefijo):
    monkeypatch.setenv("DATABASE_URL", f"{prefijo}user:clave@{NEON}")

    settings = sin_entorno()

    assert settings.database_url == f"postgresql+psycopg://user:clave@{NEON}"


def test_database_url_conserva_sslmode(sin_entorno, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"postgresql://user:clave@{NEON}&channel_binding=require")

    assert sin_entorno().database_url.endswith("?sslmode=require&channel_binding=require")


def test_database_url_gana_sobre_las_piezas(sin_entorno, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"postgresql://user:clave@{NEON}")

    settings = sin_entorno(postgres_user="u", postgres_password="p", postgres_db="local")

    assert "neon.tech" in settings.database_url


def test_sin_conexion_falla_al_iniciar(sin_entorno):
    with pytest.raises(ValidationError, match="Falta la conexión a la base"):
        sin_entorno()


def test_secret_key_corta_falla_al_iniciar(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"postgresql://user:clave@{NEON}")

    with pytest.raises(ValidationError, match="secret_key"):
        Settings(_env_file=None, secret_key="corta")


def test_docs_apagadas_por_defecto(sin_entorno, monkeypatch):
    monkeypatch.delenv("MOSTRAR_DOCS", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"postgresql://user:clave@{NEON}")

    assert sin_entorno().mostrar_docs is False


def test_database_url_con_esquema_invalido(sin_entorno, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql://user:clave@host/db")

    with pytest.raises(ValueError, match="debe empezar con postgresql://"):
        sin_entorno().database_url
