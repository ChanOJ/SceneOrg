#!/usr/bin/env bash
# Build site/ from the raw store and check it (needs ~/Code/id3x/raw). Nothing is deployed here:
# commit site/ and merge; the "Website: deploy" workflow syncs it to bunny.net.
set -euo pipefail

cd "$(dirname "$0")/.."
python3 -I scripts/build.py
python3 -I scripts/verify_build.py --rebuild
python3 -I scripts/check_excludes.py
git status --short site/ | head -20
