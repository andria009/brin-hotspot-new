FROM python:3.14-slim

ARG INSTALL_HDF=false

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      gdal-bin \
      gcc \
      libgdal-dev \
      libhdf4-alt-dev \
      libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip install --upgrade pip \
    && if [ "$INSTALL_HDF" = "true" ]; then \
      python -m pip install ".[geo,hdf]"; \
    else \
      python -m pip install ".[geo]"; \
    fi

COPY db ./db
