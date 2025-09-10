FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy API code and web assets
COPY api/pyproject.toml ./api/
COPY api/main.py ./api/
COPY web/ ./web/

# Install dependencies
RUN cd api && uv sync --no-dev

EXPOSE 8000
CMD ["uv", "run", "--directory", "api", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
