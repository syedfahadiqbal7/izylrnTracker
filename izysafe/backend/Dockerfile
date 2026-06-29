# syntax=docker/dockerfile:1
FROM python:3.12-slim

# - PYTHONUNBUFFERED: stream logs immediately
# - PYTHONDONTWRITEBYTECODE: no .pyc clutter in the mounted volume
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# psycopg2-binary and asyncpg ship manylinux wheels, so no compiler/libpq needed.
# Install deps first (layer cache), then the app source.
COPY pyproject.toml ./
RUN pip install --upgrade pip
COPY . .
RUN pip install ".[dev]"

EXPOSE 8000

# Dev default. docker-compose overrides with --reload; migrations are run
# explicitly (alembic upgrade head) in Step 6, not on container start.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
