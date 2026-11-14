# syntax=docker/dockerfile:1.7
# Image de l'app Home Assistant « HA - Pellets » (construite par le Supervisor).
FROM ghcr.io/astral-sh/uv:0.12.10-python3.12-trixie AS builder
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Europe/Paris \
    PATH="/app/.venv/bin:${PATH}" \
    PELLETS_DB_PATH=/data/pellets.db PELLETS_HOST=0.0.0.0 PELLETS_PORT=8234
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY app ./app
COPY run.sh /run.sh
RUN chmod +x /run.sh
# Tourne en root : /data (persistant, sauvegardé par HA) appartient à root.
CMD ["/run.sh"]
