FROM python:3.13-slim-bookworm

# Add uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_PYTHON_DOWNLOADS=never
RUN mkdir /app
WORKDIR /app
COPY . .
RUN uv sync --frozen --no-dev
EXPOSE 5000

CMD [".venv/bin/gunicorn", "--bind", "0.0.0.0:5000", "meridiano.app:app"]
