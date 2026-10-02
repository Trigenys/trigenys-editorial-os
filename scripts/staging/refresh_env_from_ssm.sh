#!/usr/bin/env bash
set -euo pipefail
set +x

: "${SSM_PREFIX:=/trigenys/editorial-os/staging}"
: "${AWS_REGION:=eu-west-3}"
: "${ENV_FILE:=.env}"

read_parameter() {
  local name="$1"
  aws ssm get-parameter \
    --region "$AWS_REGION" \
    --name "$SSM_PREFIX/$name" \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text
}

read_optional_parameter() {
  local name="$1"
  local fallback="$2"
  local value
  if value="$(read_parameter "$name" 2>/dev/null)"; then
    printf '%s' "$value"
  else
    printf '%s' "$fallback"
  fi
}

database_url="$(read_parameter database-url)"
payload_base_url="$(read_parameter payload-base-url)"
payload_api_token="$(read_parameter payload-api-token)"
payload_collection="$(read_optional_parameter payload-collection posts)"
payload_auth_mode="$(read_optional_parameter payload-auth-mode bearer)"
payload_auth_collection="$(read_optional_parameter payload-auth-collection users)"

if [[ "$database_url" == postgresql://* ]]; then
  database_url="postgresql+psycopg://${database_url#postgresql://}"
fi

umask 077
tmp_file="$(mktemp "${ENV_FILE}.tmp.XXXXXX")"
trap 'rm -f "$tmp_file"' EXIT

{
  printf 'EDITORIAL_OS_ENVIRONMENT=staging\n'
  printf 'EDITORIAL_OS_DEPLOYMENT_LABEL=staging\n'
  printf 'EDITORIAL_OS_DATABASE_ECHO=false\n'
  printf 'EDITORIAL_OS_DATABASE_URL=%s\n' "$database_url"
  printf 'EDITORIAL_OS_PAYLOAD_ENABLED=true\n'
  printf 'EDITORIAL_OS_PAYLOAD_BASE_URL=%s\n' "$payload_base_url"
  printf 'EDITORIAL_OS_PAYLOAD_API_TOKEN=%s\n' "$payload_api_token"
  printf 'EDITORIAL_OS_PAYLOAD_COLLECTION=%s\n' "$payload_collection"
  printf 'EDITORIAL_OS_PAYLOAD_AUTH_MODE=%s\n' "$payload_auth_mode"
  printf 'EDITORIAL_OS_PAYLOAD_AUTH_COLLECTION=%s\n' "$payload_auth_collection"
  printf 'EDITORIAL_OS_POSTIZ_ENABLED=false\n'
  printf 'EDITORIAL_OS_N8N_ENABLED=false\n'
  printf 'EDITORIAL_OS_REMOTION_ENABLED=false\n'
} > "$tmp_file"

install -m 600 "$tmp_file" "$ENV_FILE"
rm -f "$tmp_file"
trap - EXIT

unset database_url payload_base_url payload_api_token
printf 'Staging runtime environment refreshed from SSM Parameter Store.\n'
