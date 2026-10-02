#!/usr/bin/env bash
set -euo pipefail

: "${DEPLOY_ROOT:=/opt/trigenys/editorial-os/staging}"
cd "$DEPLOY_ROOT"

if [[ ! -f .release.previous.env ]]; then
  echo "No previous staging release metadata exists." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .release.previous.env
set +a
export API_IMAGE WEB_IMAGE STAGING_WEB_PORT

docker compose -f compose.staging.yml pull api web
docker compose -f compose.staging.yml up -d --remove-orphans api web
BASE_URL="http://127.0.0.1:${STAGING_WEB_PORT:-8080}" ./smoke.sh

printf 'Previous staging images restored. Database migrations were not downgraded.\n'
