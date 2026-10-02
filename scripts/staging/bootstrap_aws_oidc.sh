#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:=eu-west-3}"
: "${BOOTSTRAP_STACK_NAME:=trigenys-editorial-os-github-oidc}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

aws cloudformation validate-template \
  --region "$AWS_REGION" \
  --template-body "file://$repo_root/infra/aws/github-oidc-bootstrap.yml" >/dev/null

aws cloudformation deploy \
  --region "$AWS_REGION" \
  --stack-name "$BOOTSTRAP_STACK_NAME" \
  --template-file "$repo_root/infra/aws/github-oidc-bootstrap.yml" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset

aws cloudformation describe-stacks \
  --region "$AWS_REGION" \
  --stack-name "$BOOTSTRAP_STACK_NAME" \
  --query 'Stacks[0].Outputs[].{Key:OutputKey,Value:OutputValue}' \
  --output table
