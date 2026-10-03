FROM python:3.9.21-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini pyproject.toml ./
COPY tests ./tests
RUN useradd --create-home loop && chown -R loop:loop /app
USER loop
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
