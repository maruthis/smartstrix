# Multi-stage: build the static SPA, then serve it with nginx. Nothing in
# the runtime image needs Node — it's a plain static file server, and (per
# the repo-split plan) carries no secrets of any kind.

FROM node:20-slim AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Baked in at build time (Vite inlines import.meta.env.* into the bundle —
# it cannot be changed by setting an env var on the running container).
# Empty by default = same-origin (matches src/api/client.ts's own
# fallback) — the right default for the gateway topology in
# docker-compose.yml, where nginx proxies both frontend and /api/* from
# one origin. Only pass a non-empty VITE_API_BASE_URL build arg if the
# backend is genuinely served from a different origin than this frontend.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
