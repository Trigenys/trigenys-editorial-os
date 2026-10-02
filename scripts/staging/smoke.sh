#!/usr/bin/env bash
set -euo pipefail

: "${BASE_URL:=http://127.0.0.1:8080}"

retry() {
  local attempts="$1"
  shift
  local delay="$1"
  shift
  local count=1
  until "$@"; do
    if (( count >= attempts )); then
      return 1
    fi
    sleep "$delay"
    count=$((count + 1))
  done
}

check_web() {
  curl --fail --silent --show-error "$BASE_URL/health/web" >/dev/null
}

check_api() {
  local body
  body="$(curl --fail --silent --show-error "$BASE_URL/health/api")"
  HEALTH_BODY="$body" python - <<'PY'
import json
import os

payload = json.loads(os.environ["HEALTH_BODY"])
assert payload["status"] == "ok"
assert payload["environment"] == "staging"
assert payload["deployment"] == "staging"
PY
}

check_ready() {
  curl --fail --silent --show-error "$BASE_URL/health/ready" \
    | python -c 'import json,sys; assert json.load(sys.stdin)["status"] == "ready"'
}

retry 20 3 check_web
retry 20 3 check_api
retry 20 3 check_ready

printf 'Staging smoke test passed: web, API identity and database readiness are healthy.\n'
