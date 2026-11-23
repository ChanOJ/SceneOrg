#!/usr/bin/env bash
# Build and publish the archive from the Mac (site/ needs the raw store ~/Code/id3x/raw, so CI cannot build it):
#
#   scripts/publish.sh            build + verify -> deploy (runs verify_build and
#                                 check_excludes first, refuses on failure) -> smoke test
#   scripts/publish.sh --dry-run  same, but only shows what the deploy would upload and delete
#   scripts/publish.sh --no-build skip build (deploy the site/ already generated)
#
# Needs: python3, node, pass-cli (logged in: the bunny.net API key comes from infra/secrets.env).
set -euo pipefail

cd "$(dirname "$0")/.."
build=1 deploy_args=()
for a in "$@"; do
  case "$a" in
    --no-build) build=0 ;;
    --dry-run) deploy_args+=(--dry-run) ;;
    --allow-mass-delete) deploy_args+=(--allow-mass-delete) ;;
    *) echo "usage: $0 [--no-build] [--dry-run] [--allow-mass-delete]"; exit 1 ;;
  esac
done

if [ "$build" = 1 ]; then
  python3 -I scripts/build.py
  python3 -I scripts/verify_build.py
fi

pass-cli run --env-file infra/secrets.env -- python3 -I scripts/deploy.py ${deploy_args[@]+"${deploy_args[@]}"}

if [[ " ${deploy_args[*]-} " != *" --dry-run "* ]]; then
  python3 -I scripts/smoke_test.py --sample 300
fi
