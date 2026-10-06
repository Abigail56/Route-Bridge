FROM python:3.12-slim AS build
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim
WORKDIR /app
RUN useradd --system --create-home --uid 10001 routebridge
COPY --from=build /install /usr/local
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
ENV PYTHONPATH=/app/src PYTHONUNBUFFERED=1
USER routebridge
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"
CMD ["uvicorn", "routebridge.main:app", "--host", "0.0.0.0", "--port", "8000"]
