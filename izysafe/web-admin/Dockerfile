# syntax=docker/dockerfile:1
# Production admin panel — build the Vite app, serve it with nginx (which also
# reverse-proxies /api to the backend, so the SPA is same-origin, no CORS).

# ---- build ----
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# .env.production sets VITE_API_BASE_URL=/api/v1 (same-origin via nginx).
RUN npm run build

# ---- serve ----
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1
