# One image for every profile. The command picks the role:
#   API:     (default) migrate, then uvicorn; serves the React build from /app/web
#   Worker:  python -m app.worker
# Build from the repo root:  docker build -f deploy/Dockerfile -t lms .

# ---- frontend build ------------------------------------------------------------------------
FROM node:24-alpine AS web
WORKDIR /web
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# ---- backend ---------------------------------------------------------------------------------
FROM python:3.13-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --locked --no-dev
COPY --from=web /web/dist /app/web

RUN useradd --create-home --uid 10001 lms && mkdir -p /data/uploads && chown -R lms /data /app
USER lms
ENV PATH="/app/.venv/bin:$PATH" \
    LMS_ENVIRONMENT=production \
    LMS_FRONTEND_DIST_DIR=/app/web \
    LMS_UPLOAD_DIR=/data/uploads \
    LMS_SEED_DEMO_DATA=false
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health/live').status==200 else 1)"
# --proxy-headers: real client IPs in the API call log behind the load balancer.
# RUN_MIGRATIONS=false where several API containers start together (AWS runs one migration task per deploy).
CMD ["sh", "-c", "if [ \"${RUN_MIGRATIONS:-true}\" = true ]; then python -m app.cli migrate; fi && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips='*'"]
