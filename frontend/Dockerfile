FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
# Certificat auto-signé : nécessaire pour que les téléphones puissent ouvrir la
# caméra (getUserMedia exige un contexte sécurisé). Premier accès : avertissement
# à valider manuellement (voir docs/utilisation.md).
RUN apk add --no-cache openssl \
    && mkdir -p /etc/nginx/certs \
    && openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
       -keyout /etc/nginx/certs/arc-replay.key -out /etc/nginx/certs/arc-replay.crt \
       -subj "/CN=arc-replay"
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80 443
