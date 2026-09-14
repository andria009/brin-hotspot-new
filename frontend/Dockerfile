FROM node:22-alpine AS build

ARG VITE_KEYCLOAK_URL=https://geomimo-keycloak.brin.go.id
ARG VITE_KEYCLOAK_REALM=brin-geospatial
ARG VITE_KEYCLOAK_CLIENT_ID=hotspot-new
ENV VITE_KEYCLOAK_URL=$VITE_KEYCLOAK_URL \
    VITE_KEYCLOAK_REALM=$VITE_KEYCLOAK_REALM \
    VITE_KEYCLOAK_CLIENT_ID=$VITE_KEYCLOAK_CLIENT_ID

WORKDIR /app

COPY frontend/package*.json ./
RUN npm ci

COPY frontend ./
RUN npm run build

FROM nginx:1.29-alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
