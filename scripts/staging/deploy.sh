#!/usr/bin/env bash
set -euo pipefail

if (( $# != 2 )); then
  echo "Usage: $0 <api-image> <web-image>" >&2
  exit 64
fi

API_IMAGE="$1"
WEB_IMAGE="$2"
export API_IMAGE WEB_IMAGE

: "${AWS_REGION:=eu-west-3}"
: "${DEPLOY_ROOT:=/opt/trigenys/editorial-os/staging}"
: "${STAGING_WEB_PORT:=8080}"
export STAGING_WEB_PORT

cd "$DEPLOY_ROOT"

: "${SSM_PREFIX:=/trigenys/editorial-os/staging}"

ghcr_token="$(
  aws ssm get-parameter \
    --region "$AWS_REGION" \
    --name "$SSM_PREFIX/ghcr-token" \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text
)"
ghcr_user="$(
  aws ssm get-parameter \
    --region "$AWS_REGION" \
    --name "$SSM_PREFIX/ghcr-user" \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text 2>/dev/null || printf 'EagleFox31'
)"
printf '%s' "$ghcr_token" | docker login ghcr.io --username "$ghcr_user" --password-stdin >/dev/null
unset ghcr_token ghcr_user

./refresh_env_from_ssm.sh

if [[ -f .release.env ]]; then
  cp .release.env .release.previous.env
fi

umask 077
cat > .release.env <<EOF
API_IMAGE=$API_IMAGE
WEB_IMAGE=$WEB_IMAGE
STAGING_WEB_PORT=$STAGING_WEB_PORT
EOF
chmod 600 .release.env

docker compose -f compose.staging.yml pull migrate api web
docker compose -f compose.staging.yml run --rm migrate
docker compose -f compose.staging.yml run --rm api \
  python /app/scripts/insight_pilot.py seed-sources
docker compose -f compose.staging.yml run --rm api \
  python /app/scripts/staging/check_payload.py
docker compose -f compose.staging.yml up -d --remove-orphans api web

BASE_URL="http://127.0.0.1:$STAGING_WEB_PORT" ./smoke.sh

printf 'Staging revision deployed successfully.\n'
