"""Validación de fotos recibidas. Por ahora no se guardan en ningún lado."""

from fastapi import UploadFile

from app.exceptions import FotoInvalida, FotoMuyGrande, FotoVacia

MAXIMO_MB = 10
MAXIMO_BYTES = MAXIMO_MB * 1024 * 1024


def _tipo_real(inicio: bytes) -> str | None:
    """Detecta el formato por los primeros bytes del archivo ("firma").

    No se confía en el Content-Type ni en la extensión: los manda el cliente
    y se pueden falsificar.
    """
    if inicio.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if inicio.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if inicio[:4] == b"RIFF" and inicio[8:12] == b"WEBP":
        return "image/webp"
    return None


async def validar_foto(foto: UploadFile) -> tuple[str, bytes]:
    """Lee la foto y devuelve (tipo real, contenido).

    Lanza FotoVacia, FotoMuyGrande o FotoInvalida.
    """
    # Lee como máximo un byte más del límite: alcanza para saber si se pasa
    # sin cargar en memoria un archivo enorme.
    contenido = await foto.read(MAXIMO_BYTES + 1)
    if not contenido:
        raise FotoVacia()
    if len(contenido) > MAXIMO_BYTES:
        raise FotoMuyGrande(MAXIMO_MB)
    tipo = _tipo_real(contenido[:12])
    if tipo is None:
        raise FotoInvalida()
    return tipo, contenido
