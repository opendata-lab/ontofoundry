# One image, one role: the OntoFoundry API.
#
# Agent execution used to live here — a Node runtime for the Pi cell, a second
# `runner` image with a docker CLI to spawn sandbox containers, and a shared
# base to make them interchangeable. All of it now belongs to an external
# OpenDataWorks DataAgent, so what remains is a Python service.

FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /opt/ontofoundry-api

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/pyproject.toml apps/api/README.md* /opt/ontofoundry-api/
COPY apps/api/src /opt/ontofoundry-api/src
RUN pip install --no-cache-dir /opt/ontofoundry-api

# ---- of-backend --------------------------------------------------------
FROM base AS backend

EXPOSE 8900

# Migrations are owned by ontofoundry_api; alembic reads its config from inside
# the installed package.
CMD ["sh", "-c", "alembic -c /opt/ontofoundry-api/src/ontofoundry_api/alembic.ini upgrade head && uvicorn ontofoundry_api.main:app --host 0.0.0.0 --port 8900"]
