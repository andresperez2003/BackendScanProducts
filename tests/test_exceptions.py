from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.exceptions import AppError, registrar_manejadores


class ErrorDePrueba(AppError):
    status_code = 418


def test_manejador_app_error():
    app = FastAPI()
    registrar_manejadores(app)

    @app.get("/falla")
    def falla():
        raise ErrorDePrueba("mensaje de prueba")

    respuesta = TestClient(app).get("/falla")

    assert respuesta.status_code == 418
    assert respuesta.json() == {"detail": "mensaje de prueba"}


class ErrorConHeaders(AppError):
    status_code = 401
    headers = {"WWW-Authenticate": "Bearer"}


def test_manejador_app_error_con_headers():
    app = FastAPI()
    registrar_manejadores(app)

    @app.get("/falla")
    def falla():
        raise ErrorConHeaders("no autenticado")

    respuesta = TestClient(app).get("/falla")

    assert respuesta.status_code == 401
    assert respuesta.headers["WWW-Authenticate"] == "Bearer"
