FROM node:24-alpine AS build

WORKDIR /app
COPY package.json tsconfig.json vite.config.ts index.html ./
COPY src ./src

ARG VITE_DEPLOYMENT_LABEL=staging
ENV VITE_DEPLOYMENT_LABEL=$VITE_DEPLOYMENT_LABEL

RUN npm install --ignore-scripts
RUN npm run build

FROM nginx:1.29-alpine

COPY deploy/nginx.staging.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=4 \
  CMD wget -q -O /dev/null http://127.0.0.1/health/web || exit 1
