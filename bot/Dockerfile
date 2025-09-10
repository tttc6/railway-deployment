FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy bot code and deps
COPY bot/pyproject.toml ./bot/
COPY bot/main.py ./bot/

# Install dependencies
RUN cd bot && uv sync --no-dev

CMD ["uv", "run", "--directory", "bot", "python", "main.py"]
