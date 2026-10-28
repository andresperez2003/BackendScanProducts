from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.exceptions import registrar_manejadores
from app.routers import admin, auth, empresas, products, suppliers, trackings

docs = get_settings().mostrar_docs
app = FastAPI(
    title="ScanProducts API",
    docs_url="/docs" if docs else None,
    redoc_url="/redoc" if docs else None,
    openapi_url="/openapi.json" if docs else None,
)

registrar_manejadores(app)

# Permite que el frontend (otro origen, ej. http://localhost:5173) llame a la API.
# El token viaja en el header Authorization, no en cookies: no hace falta
# allow_credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_lista,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    # Para que el frontend pueda leer cuánto falta de un bloqueo de login (429).
    expose_headers=["Retry-After"],
)

app.include_router(auth.router)
app.include_router(empresas.router)
app.include_router(suppliers.router)
app.include_router(products.router)
app.include_router(trackings.router)
app.include_router(admin.router)


@app.get("/")
def hola_mundo():
    return {"mensaje": "Hola mundo"}
