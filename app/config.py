from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Producción (ej. Neon): la cadena de conexión completa, con ?sslmode=require.
    # Si está definida, se usa en lugar de las piezas sueltas de abajo.
    database_url_completa: str | None = Field(default=None, validation_alias="DATABASE_URL")

    # Desarrollo (Docker local): la conexión se arma con estas piezas.
    postgres_user: str | None = None
    postgres_password: str | None = None
    postgres_db: str | None = None
    db_host: str = "localhost"
    db_port: int = 5432
    # Firma los tokens: con una clave corta se pueden adivinar y falsificar.
    secret_key: str = Field(min_length=32)
    # Documentación interactiva (/docs, /redoc, /openapi.json). Apagada por
    # defecto para no publicar el mapa de la API; docker-compose.yml la enciende.
    mostrar_docs: bool = False
    access_token_expire_minutes: int = 30
    max_intentos_login: int = 5
    minutos_bloqueo_login: int = 10
    # Orígenes del frontend que pueden llamar a la API, separados por comas.
    cors_origins: str = "http://localhost:5173"
    # Lectura automática de lote y vencimiento en la foto (OpenRouter).
    # Sin la clave, el endpoint de la foto responde 503 y se llena a mano.
    openrouter_api_key: str | None = None
    openrouter_model: str = "qwen/qwen3-vl-plus"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_segundos: float = 60
    # Máximo de lecturas de fotos por minuto por empresa, aunque le queden en
    # el plan: frena scripts o clics repetidos.
    lecturas_por_minuto: int = 6
    # Contacto del equipo para adquirir un plan; se muestra cuando una empresa
    # se queda sin lecturas. WhatsApp con indicativo y sin "+" (ej. 573001234567).
    soporte_whatsapp: str | None = None
    soporte_correo: str | None = None

    @property
    def cors_origins_lista(self) -> list[str]:
        return [origen.strip() for origen in self.cors_origins.split(",") if origen.strip()]

    @model_validator(mode="after")
    def _hay_conexion(self):
        piezas = (self.postgres_user, self.postgres_password, self.postgres_db)
        if not self.database_url_completa and not all(piezas):
            raise ValueError(
                "Falta la conexión a la base: define DATABASE_URL o "
                "POSTGRES_USER, POSTGRES_PASSWORD y POSTGRES_DB"
            )
        return self

    @property
    def database_url(self) -> str:
        if self.database_url_completa:
            return _con_driver_psycopg(self.database_url_completa)
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.db_host}:{self.db_port}/{self.postgres_db}"
        )


def _con_driver_psycopg(url: str) -> str:
    """Neon, Render, Railway, etc. dan la URL como postgresql:// o postgres://;
    SQLAlchemy necesita que diga qué driver usar (psycopg 3). Los parámetros
    como ?sslmode=require se conservan."""
    for prefijo in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg://" + url.removeprefix(prefijo)
    raise ValueError("DATABASE_URL debe empezar con postgresql:// o postgres://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
