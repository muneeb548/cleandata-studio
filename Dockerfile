# CleanData Studio — one container that serves both the website and the API.
# Build:  docker build -t cleandata-studio --build-arg VITE_SITE_URL=https://your-domain .
# Run:    docker run -p 8000:8000 cleandata-studio      → http://localhost:8000

# ---------- 1. Build the frontend (static files) ----------
FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
COPY frontend/ ./
# Public values only — everything starting with VITE_ ends up in the browser bundle.
ARG VITE_SITE_URL=""
ARG VITE_CONTACT_EMAIL=""
ARG VITE_GITHUB_URL=""
# Provided automatically by Railway; used when VITE_SITE_URL is not set.
ARG RAILWAY_PUBLIC_DOMAIN=""
RUN if [ -z "$VITE_SITE_URL" ] && [ -n "$RAILWAY_PUBLIC_DOMAIN" ]; then VITE_SITE_URL="https://$RAILWAY_PUBLIC_DOMAIN"; fi \
 && echo "Building frontend for site URL: ${VITE_SITE_URL:-<not set>}" \
 && VITE_SITE_URL="$VITE_SITE_URL" VITE_CONTACT_EMAIL="$VITE_CONTACT_EMAIL" VITE_GITHUB_URL="$VITE_GITHUB_URL" npm run build

# ---------- 2. Python runtime ----------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /build/frontend/dist ./frontend_dist

# Run as an unprivileged user. Uploads are written only to the system temp folder
# (deleted right after import) — nothing is stored in the image or on a volume.
RUN useradd --create-home --uid 10001 appuser
USER appuser

ENV ENVIRONMENT=production \
    FRONTEND_DIST=/app/frontend_dist \
    PORT=8000
EXPOSE 8000

# Used by Docker / docker compose. Hosting platforms use their own health-check setting (/api/health).
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/api/health', timeout=4)" || exit 1

# Exactly ONE worker: sessions live in this process's memory (see DEPLOYMENT.md).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-server-header --timeout-keep-alive 30"]
