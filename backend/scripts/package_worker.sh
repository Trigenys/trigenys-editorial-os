#!/usr/bin/env bash
set -euo pipefail

mode="${1:-}"
config_arg="${2:-}"
outdir_arg="${3:-}"

if [[ "$mode" != "dry-run" && "$mode" != "deploy" ]]; then
  echo "Usage: $0 <dry-run|deploy> <wrangler-config> [outdir]" >&2
  exit 2
fi

if [[ -z "$config_arg" ]]; then
  echo "Wrangler config path is required." >&2
  exit 2
fi

backend_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo_root="$(cd "$backend_dir/.." && pwd)"

if [[ "$config_arg" = /* ]]; then
  config_path="$config_arg"
else
  config_path="$backend_dir/$config_arg"
fi

if [[ ! -f "$config_path" ]]; then
  echo "Wrangler config not found: $config_path" >&2
  exit 1
fi

python -m pip install --user --quiet uv
export PATH="$HOME/.local/bin:$PATH"

cd "$repo_root"
npm install --ignore-scripts
npm run build
python scripts/cloudflare/prepare_spike.py

cd "$repo_root/cloudflare"
uv sync --group dev
uv run pywrangler sync --force

# Wrangler resolves python_modules from the directory containing the user
# Wrangler config. AppFactory writes its reconciled config under /backend,
# while pywrangler vendors dependencies under /cloudflare. Mirror the vendor
# tree beside the effective config for the duration of the deploy so packages
# such as pydantic_settings are actually uploaded with the Worker.
vendor_source="$repo_root/cloudflare/python_modules"
config_root="$(cd "$(dirname "$config_path")" && pwd)"
vendor_target="$config_root/python_modules"

if [[ ! -d "$vendor_source" ]]; then
  echo "Pywrangler vendor directory not found: $vendor_source" >&2
  exit 1
fi

cleanup_vendor() {
  if [[ "$vendor_target" != "$vendor_source" ]]; then
    rm -rf "$vendor_target"
  fi
}
trap cleanup_vendor EXIT

if [[ "$vendor_target" != "$vendor_source" ]]; then
  rm -rf "$vendor_target"
  cp -a "$vendor_source" "$vendor_target"
fi

if [[ ! -d "$vendor_target/pydantic_settings" ]]; then
  echo "Expected vendored dependency pydantic_settings is missing from $vendor_target" >&2
  exit 1
fi

if [[ "$mode" == "dry-run" ]]; then
  if [[ -z "$outdir_arg" ]]; then
    echo "Dry-run output directory is required." >&2
    exit 2
  fi
  if [[ "$outdir_arg" = /* ]]; then
    outdir_path="$outdir_arg"
  else
    outdir_path="$backend_dir/$outdir_arg"
  fi
  rm -rf "$outdir_path"
  npx --yes wrangler deploy --dry-run --config "$config_path" --outdir "$outdir_path"
else
  npx --yes wrangler deploy --config "$config_path" --keep-vars
fi
