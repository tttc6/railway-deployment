FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy bot code and deps
COPY . ./bot/

# Install dependencies
RUN cd bot && uv sync --no-dev

CMD ["uv", "run", "--no-dev", "--directory", "bot", "python", "main.py"]
