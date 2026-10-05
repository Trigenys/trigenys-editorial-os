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
  uv run pywrangler deploy     --dry-run     --config "$config_path"     --outdir "$outdir_path"
else
  uv run pywrangler deploy     --config "$config_path"     --keep-vars
fi
