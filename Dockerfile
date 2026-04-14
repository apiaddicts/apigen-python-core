FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1

COPY uv.lock pyproject.toml /app/

RUN uv sync --frozen --no-install-project --no-dev

COPY src/ src/
COPY README.md .

RUN uv sync --frozen --no-dev

CMD ["uv", "run", "python", "-m", "pip", "freeze"]
