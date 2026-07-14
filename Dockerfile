# Stage 1: Build frontend
FROM node:22-alpine AS frontend-build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json tsconfig.app.json tsconfig.node.json vite.config.ts index.html ./
COPY src/ src/
COPY public/ public/
RUN npm run build

# Stage 2: Runtime — Python backend + frontend dist
FROM python:3.12-slim
WORKDIR /app

# Install runtime deps
COPY sidecar/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt uvicorn

# Copy backend code
COPY sidecar/ sidecar/
COPY sentinel/ sentinel/

# Copy frontend build
COPY --from=frontend-build /app/dist/ dist/

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/api/health')" || exit 1

ENTRYPOINT ["uvicorn", "sidecar.main:app", "--host", "0.0.0.0", "--port", "8765"]
