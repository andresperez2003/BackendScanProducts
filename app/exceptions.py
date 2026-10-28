import math
from datetime import timedelta

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Error de dominio que se traduce a una respuesta HTTP."""

    status_code: int = 400
    headers: dict[str, str] | None = None

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class UsuarioYaExiste(AppError):
    """El usuario solicitado ya pertenece a otra empresa."""

    status_code = 409

    def __init__(self, usuario: str):
        self.usuario = usuario
        super().__init__(f"El usuario '{usuario}' ya está en uso")


class CredencialesInvalidas(AppError):
    """Usuario o contraseña incorrectos (mismo mensaje para ambos casos)."""

    status_code = 401
    headers = {"WWW-Authenticate": "Bearer"}

    def __init__(self):
        super().__init__("Usuario o contraseña incorrectos")


class ContrasenaActualIncorrecta(AppError):
    """Al cambiar la contraseña, la actual no coincide.

    Es 400 y no 401 para que el cliente no lo confunda con un token inválido.
    """

    status_code = 400

    def __init__(self):
        super().__init__("La contraseña actual es incorrecta")


class CuentaBloqueada(AppError):
    """Demasiados intentos fallidos: el usuario queda bloqueado un tiempo."""

    status_code = 429

    def __init__(self, restante: timedelta):
        segundos = max(1, math.ceil(restante.total_seconds()))
        minutos = math.ceil(segundos / 60)
        self.headers = {"Retry-After": str(segundos)}
        super().__init__(
            f"Demasiados intentos fallidos. Intenta de nuevo en {minutos} minuto(s)"
        )


class TokenInvalido(AppError):
    """Falta el token, está expirado, mal firmado o su empresa ya no existe."""

    status_code = 401
    headers = {"WWW-Authenticate": "Bearer"}

    def __init__(self, detail: str = "Token inválido o expirado"):
        super().__init__(detail)


class SinPermiso(AppError):
    """La empresa autenticada intenta ver o modificar otra empresa."""

    status_code = 403

    def __init__(self):
        super().__init__("No tienes permiso sobre esta empresa")


class ProveedorNoEncontrado(AppError):
    """No existe o pertenece a otra empresa (no se revela cuál de los dos)."""

    status_code = 404

    def __init__(self):
        super().__init__("Proveedor no encontrado")


class ProductoNoEncontrado(AppError):
    """No existe o pertenece a otra empresa (no se revela cuál de los dos)."""

    status_code = 404

    def __init__(self):
        super().__init__("Producto no encontrado")


class ProveedorConProductos(AppError):
    """No se puede eliminar un proveedor que todavía tiene productos."""

    status_code = 409

    def __init__(self):
        super().__init__("El proveedor tiene productos asociados")


class SeguimientoNoEncontrado(AppError):
    """No existe o pertenece a otra empresa (no se revela cuál de los dos)."""

    status_code = 404

    def __init__(self):
        super().__init__("Seguimiento no encontrado")


class ProductoConSeguimientos(AppError):
    """No se puede eliminar un producto que todavía tiene seguimientos."""

    status_code = 409

    def __init__(self):
        super().__init__("El producto tiene seguimientos asociados")


class LoteDuplicado(AppError):
    """El producto ya tiene un seguimiento con ese número de lote."""

    status_code = 409

    def __init__(self, batch: str):
        self.batch = batch
        super().__init__(f"El lote '{batch}' ya existe para este producto")


class FotoInvalida(AppError):
    """El archivo no es una imagen JPEG, PNG o WebP."""

    status_code = 415

    def __init__(self):
        super().__init__("La foto debe ser una imagen JPEG, PNG o WebP")


class FotoMuyGrande(AppError):
    status_code = 413

    def __init__(self, maximo_mb: int):
        super().__init__(f"La foto no puede pesar más de {maximo_mb} MB")


class FotoVacia(AppError):
    status_code = 422

    def __init__(self):
        super().__init__("La foto está vacía")


class LecturaNoConfigurada(AppError):
    """Falta OPENROUTER_API_KEY: no se puede leer la foto automáticamente."""

    status_code = 503

    def __init__(self):
        super().__init__("La lectura automática de fotos no está configurada")


class LecturaFallida(AppError):
    """OpenRouter no respondió, tardó demasiado o devolvió algo que no se entiende."""

    status_code = 502

    def __init__(self, causa: str | None = None, modelo: str | None = None):
        super().__init__(
            "No se pudo leer la foto automáticamente. Inténtalo de nuevo o "
            "ingresa los datos a mano"
        )
        # Para diagnosticar desde la consola del navegador; no se muestra al usuario.
        self.extra = {"causa": causa, "modelo": modelo}


class LecturaSaturada(AppError):
    """OpenRouter respondió 429: está recibiendo demasiadas peticiones."""

    status_code = 429
    headers = {"Retry-After": "30"}

    def __init__(self, modelo: str | None = None):
        super().__init__(
            "El servicio de lectura está ocupado. Espera unos segundos e inténtalo de nuevo"
        )
        self.extra = {"codigo": "lectura_saturada", "modelo": modelo}


class SinLecturas(AppError):
    """La empresa no tiene plan, gastó sus lecturas o el plan venció.

    `codigo` permite al frontend distinguirlo de otros 403; `motivo` es
    "sin_plan", "vencido" o "agotado"; `soporte` es el contacto para adquirir
    o renovar un plan ({"whatsapp": ..., "correo": ...}).
    """

    status_code = 403

    def __init__(self, detail: str, motivo: str, soporte: dict[str, str | None]):
        super().__init__(detail)
        self.extra = {"codigo": "sin_lecturas", "motivo": motivo, "soporte": soporte}


class DemasiadasLecturas(AppError):
    """La empresa superó las lecturas por minuto (LECTURAS_POR_MINUTO)."""

    status_code = 429

    def __init__(self, restante: timedelta):
        segundos = max(1, math.ceil(restante.total_seconds()))
        self.headers = {"Retry-After": str(segundos)}
        super().__init__(
            f"Leíste muchas fotos seguidas. Espera {segundos} segundo(s) e inténtalo de nuevo"
        )
        self.extra = {"codigo": "demasiadas_lecturas"}


class EmpresaNoEncontrada(AppError):
    status_code = 404

    def __init__(self):
        super().__init__("Empresa no encontrada")


class PlanNoEncontrado(AppError):
    status_code = 404

    def __init__(self):
        super().__init__("Plan no encontrado")


class PlanDuplicado(AppError):
    """Ya hay otro plan con ese nombre."""

    status_code = 409

    def __init__(self, nombre: str):
        super().__init__(f"Ya existe un plan llamado '{nombre}'")


class PlanInactivo(AppError):
    """Un plan desactivado no se puede asignar a más empresas."""

    status_code = 409

    def __init__(self, nombre: str):
        super().__init__(f"El plan {nombre} está desactivado: actívalo antes de asignarlo")


async def manejar_app_error(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, **getattr(exc, "extra", {})},
        headers=exc.headers,
    )


async def manejar_error_validacion(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Igual que el 422 de FastAPI, pero sin "input".

    "input" repite lo que mandó el cliente, incluida la contraseña, y eso
    puede terminar guardado en logs o herramientas de monitoreo.
    """
    errores = [
        {campo: valor for campo, valor in error.items() if campo != "input"}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errores)})


def registrar_manejadores(app: FastAPI) -> None:
    app.add_exception_handler(AppError, manejar_app_error)
    app.add_exception_handler(RequestValidationError, manejar_error_validacion)
