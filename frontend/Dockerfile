# Multi-stage build: compile the React app, then serve it with nginx.
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Served next to the backend via nginx's /api proxy (LAN mode), so the API is same-origin.
ARG VITE_SAME_ORIGIN_API=true
ENV VITE_SAME_ORIGIN_API=$VITE_SAME_ORIGIN_API
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
# The local build talks to its own origin; no published ngrok address is needed.
RUN printf '{\n  "apiBaseUrl": ""\n}\n' > /usr/share/nginx/html/config.json
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/healthz || exit 1
