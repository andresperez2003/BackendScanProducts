FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

# DEV=true instala también las dependencias de testing
ARG DEV=false

COPY requirements.txt requirements-dev.txt ./
RUN if [ "$DEV" = "true" ]; then         pip install --no-cache-dir -r requirements-dev.txt;     else         pip install --no-cache-dir -r requirements.txt;     fi

COPY . .

# Sin root: si alguien aprovecha una falla de la API, no controla el contenedor
RUN useradd --create-home --uid 1000 app
USER app

EXPOSE 8000

# Producción (Render): aplica las migraciones pendientes y arranca la API en el
# puerto que asigna Render ($PORT; 8000 si no hay). --proxy-headers: Render pone
# un proxy HTTPS delante y así la API ve la IP real del cliente.
# En local docker-compose.yml reemplaza este comando por uno con --reload.
CMD alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips="*"
