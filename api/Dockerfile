FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy API code and static assets
COPY . ./api/

# Install dependencies
RUN cd api && uv sync --no-dev

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "--directory", "api", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
