#!/usr/bin/env bash
# One-time setup of this repository (adapted from OrangeJuice98, vault OldSites).
#
#   scripts/bootstrap.sh new <repo> <storage-zone> <pull-zone> <hostname>
#       site.json for a site with NO zone on bunny.net yet (the first apply creates everything),
#       the OpenTofu state passphrase item <repo>-tofu-state-passphrase generated in Proton Pass
#       if missing (never shown), its reference in infra/secrets.env, offline OpenTofu validation. Nothing is created on bunny.net.
#   scripts/bootstrap.sh github
#       public GitHub repository <owner>/<repo> of site.json (if missing), its secrets
#       BUNNY_API_KEY and TF_VAR_STATE_PASSPHRASE read from Proton Pass, and the origin remote.
#
# Needs: pass-cli (logged in), gh (logged in), tofu, jq, python3, node.
set -euo pipefail

cd "$(dirname "$0")/.."
VAULT=OldSites

cmd_new() {
  local repo=$1 zone=$2 pz=$3 host=$4
  [ -n "$repo" ] && [ -n "$zone" ] && [ -n "$pz" ] && [ -n "$host" ] || { echo "usage: $0 new <repo> <storage-zone> <pull-zone> <hostname>"; exit 1; }
  local owner
  owner=$(jq -r '.owner // empty' site.json 2>/dev/null || true)
  jq -n --arg owner "${owner:-ChanOJ}" --arg repo "$repo" --arg zone "$zone" --arg pz "$pz" --arg host "$host" \
    '{owner: $owner, repo: $repo, storage_zone: $zone, pullzone: $pz, hostname: $host, not_found_page: "/404.html"}' > site.json
  cat site.json

  # This site gets its own state passphrase (the API key item is shared by the old sites).
  local item="$repo-tofu-state-passphrase"
  if pass-cli item list --vault-name "$VAULT" | grep -q ": $item "; then
    echo "Proton Pass item $item already exists."
  else
    pass-cli item create login --vault-name "$VAULT" --title "$item" --generate-password=40 >/dev/null
    echo "Proton Pass item $item created."
  fi
  sed -i '' -e "s|^TF_VAR_state_passphrase=.*|TF_VAR_state_passphrase=pass://$VAULT/$item/password|" infra/secrets.env

  (cd infra && rm -f terraform.tfstate \
    && TF_VAR_state_passphrase=validate-only-passphrase tofu init -input=false -backend=false >/dev/null \
    && TF_VAR_state_passphrase=validate-only-passphrase tofu validate)
}

cmd_github() {
  local repo owner
  repo=$(jq -r .repo site.json)
  owner=$(jq -r '.owner // empty' site.json)
  [ -n "$owner" ] || owner=$(gh api user --jq .login)
  if gh repo view "$owner/$repo" >/dev/null 2>&1; then
    echo "Repository $owner/$repo already exists."
  else
    gh repo create "$owner/$repo" --public --description "Static archive of the Scene.org home page as served by the id3 engine (2000), $(jq -r .hostname site.json), hosted on bunny.net"
  fi
  # Secrets go from Proton Pass to GitHub through stdin: never shown nor written.
  # shellcheck disable=SC2016
  pass-cli run --env-file infra/secrets.env -- sh -c '
    printf %s "$BUNNYNET_API_KEY" | gh secret set BUNNY_API_KEY --repo "$1"
    printf %s "$TF_VAR_state_passphrase" | gh secret set TF_VAR_STATE_PASSPHRASE --repo "$1"
  ' sh "$owner/$repo"
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$owner/$repo.git"
}

case "${1:-}" in
  new) shift; cmd_new "${1:-}" "${2:-}" "${3:-}" "${4:-}" ;;
  github) cmd_github ;;
  *) echo "usage: $0 new <repo> <storage-zone> <pull-zone> <hostname> | github"; exit 1 ;;
esac
