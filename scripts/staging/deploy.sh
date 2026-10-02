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

registry="${API_IMAGE%%/*}"
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$registry" >/dev/null

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
docker compose -f compose.staging.yml up -d --remove-orphans api web

BASE_URL="http://127.0.0.1:$STAGING_WEB_PORT" ./smoke.sh
python /app/does-not-exist 2>/dev/null || true

printf 'Staging revision deployed successfully.\n'
