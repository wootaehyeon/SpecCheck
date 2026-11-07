FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SERVE_FRONTEND=true \
    CORS_ORIGINS="" \
    MONITORING_ENABLED=true \
    MONITORING_DATABASE_URL=sqlite:////app/backend/data/monitoring.db

WORKDIR /app

# Install the web runtime without downloading optional ML models or test tools.
COPY backend/requirements-web.txt /app/backend/requirements-web.txt
RUN python -m pip install -r /app/backend/requirements-web.txt

RUN groupadd --gid 10001 speccheck \
    && useradd --uid 10001 --gid speccheck --no-create-home speccheck

COPY backend/app /app/backend/app
COPY backend/data/cpu_benchmark.json backend/data/gpu_benchmark.json /app/backend/data/
COPY datasets /app/datasets
COPY frontend/web /app/frontend/web
# The monitoring page builds a downloadable Windows Agent ZIP from these files.
COPY agent/speccheck_agent /app/agent/speccheck_agent
COPY agent/Start-SpecCheck.cmd /app/agent/Start-SpecCheck.cmd

RUN chown -R speccheck:speccheck /app/backend/data
USER speccheck

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8000"]
