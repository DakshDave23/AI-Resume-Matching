# syntax=docker/dockerfile:1
# The web app: built with Node, served by nginx, which also proxies /api to the backend.
# The browser talks to one origin, so no CORS setup is needed.

# 1. Build the static files.
FROM node:22.23.5-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Same origin as the page: nginx forwards /api/ to the backend container.
ENV VITE_API_BASE_URL=/api/v1
RUN npm run build

# 2. Serve them (unprivileged nginx listens on 8080 and runs as a non-root user).
FROM nginxinc/nginx-unprivileged:1.30.6-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
