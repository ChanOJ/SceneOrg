#!/usr/bin/env python3
"""Synchronise site/ (+ hosting/404.html) to the bunny.net storage zone of site.json, then purge the CDN.

Run by CI on merge (site/ is committed; generated on the Mac by scripts/build.py):

  python3 -I scripts/deploy.py [--dry-run]     # CI, BUNNY_API_KEY from the repository secret
  pass-cli run --env-file infra/secrets.env -- python3 -I scripts/deploy.py   # manual, from the Mac

- Refuses to run unless scripts/verify_build.py and scripts/check_excludes.py pass on this exact
  build: it runs them itself, then records a stamp (tmp/deploy-checks.json, the SHA-256 of every
  file and of the check scripts) so a re-run of the same build skips them.
- Uploads only new or changed files (SHA-256 compared with the checksums of the remote listing),
  in parallel; never uploads .DS_Store. Idempotent: after an interruption or failed uploads, run
  it again and only what is still missing or different is sent.
- Deletes remote files that are not in the build (guarded against mass deletion), after the
  uploads; purges the pull zone cache when something changed.

Environment: BUNNY_API_KEY or BUNNYNET_API_KEY (account API key; the storage zone password and the
pull zone id are looked up from it). DEPLOY_ENV optional label for the summary.

No network, no secret:
  python3 -I scripts/deploy.py --local-check   # checks + local manifest (what would be compared)
  python3 -I scripts/deploy.py --self-test     # unit test of the diff logic
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python3 -I leaves the script folder out
import bunny  # noqa: E402

# Local files never uploaded.
SKIP = [".DS_Store", "*/.DS_Store"]

# Refuse to delete more than this share of the remote files (and at least
# MIN_DELETE_GUARD files) without --allow-mass-delete.
MAX_DELETE_RATIO = 0.25
MIN_DELETE_GUARD = 10

# Hosting files outside site/: published path -> file in the repository.
EXTRA_FILES = {"404.html": bunny.HOSTING_DIR / "404.html"}

CHECKS = ["scripts/verify_build.py", "scripts/check_excludes.py"]
STAMP = bunny.REPO_ROOT / "tmp" / "deploy-checks.json"
LIST_LIMIT = 50  # files listed by name in the summary


def local_manifest() -> dict[str, Path]:
    files = {}
    for p in sorted(bunny.SITE_DIR.rglob("*")):
        rel = p.relative_to(bunny.SITE_DIR).as_posix()
        if p.is_file() and not any(fnmatch.fnmatchcase(rel, s) for s in SKIP):
            files[rel] = p
    for rel, p in EXTRA_FILES.items():
        files.setdefault(rel, p)
    return files


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def checksums(files: dict[str, Path], workers: int) -> dict[str, str]:
    with ThreadPoolExecutor(workers) as pool:
        return dict(zip(files, pool.map(sha256_file, files.values())))


def fingerprint(sums: dict[str, str]) -> str:
    """Identifies the build and the checks run on it."""
    h = hashlib.sha256()
    for rel in sorted(sums):
        h.update(f"{rel}\0{sums[rel]}\n".encode())
    for script in CHECKS + ["scripts/exclude-globs.txt"]:
        h.update(f"{script}\0{sha256_file(bunny.REPO_ROOT / script)}\n".encode())
    return h.hexdigest()


def ensure_checks(fp: str) -> None:
    """Run verify_build.py and check_excludes.py unless they already passed on this build."""
    try:
        if json.loads(STAMP.read_text()).get("fingerprint") == fp:
            print("Checks already passed on this exact build (tmp/deploy-checks.json).", flush=True)
            return
    except (OSError, ValueError):
        pass
    for script in CHECKS:
        print(f"Running {script}...", flush=True)
        r = subprocess.run([sys.executable, "-I", str(bunny.REPO_ROOT / script)], cwd=bunny.REPO_ROOT)
        if r.returncode != 0:
            sys.exit(f"{script} failed: nothing deployed.")
    STAMP.parent.mkdir(exist_ok=True)
    STAMP.write_text(json.dumps({"fingerprint": fp, "date": time.strftime("%Y-%m-%d %H:%M:%S")}) + "\n")


def plan(sums: dict[str, str], remote: dict[str, str | None], remote_dirs: set[str]) -> dict[str, list[str]]:
    """What to upload and delete. Pure function (see --self-test)."""
    uploads = sorted(rel for rel in sums if remote.get(rel) != sums[rel])
    orphans = sorted(rel for rel in remote if rel not in sums)
    local_dirs = set()
    for rel in sums:
        parts = rel.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            local_dirs.add("/".join(parts[:i]))
    orphan_dirs = sorted(d for d in remote_dirs if d not in local_dirs)
    # keep only the topmost orphan folders: deleting a folder deletes its content
    top = set(orphan_dirs)
    orphan_dirs = [d for d in orphan_dirs if not any(d.startswith(o + "/") for o in top if o != d)]
    loose = [f for f in orphans if not any(f.startswith(d + "/") for d in orphan_dirs)]
    return {"uploads": uploads, "orphans": orphans, "orphan_dirs": orphan_dirs, "loose": loose}


def delete_guard(n_orphans: int, n_remote: int) -> int:
    return max(MIN_DELETE_GUARD, int(n_remote * MAX_DELETE_RATIO))


def self_test() -> int:
    a, b, c = "A" * 64, "B" * 64, "C" * 64
    local = {"index.html": a, "skin/pl/index.html": b, "404.html": c, "news/page-2.html": a}
    remote = {"index.html": a, "skin/pl/index.html": a, "old.html": a,
              "gone/x.html": a, "gone/sub/y.html": a, "news/stale.html": b, "404.html": None}
    p = plan(local, remote, {"skin", "skin/pl", "gone", "gone/sub", "news"})
    expected = {
        "uploads": ["404.html", "news/page-2.html", "skin/pl/index.html"],  # changed, new, no checksum
        "orphans": ["gone/sub/y.html", "gone/x.html", "news/stale.html", "old.html"],
        "orphan_dirs": ["gone"],  # topmost only; news/ still holds a local file
        "loose": ["news/stale.html", "old.html"],
    }
    assert p == expected, p
    assert plan(local, {r: s for r, s in local.items()}, {"skin", "skin/pl", "news"}) == \
        {"uploads": [], "orphans": [], "orphan_dirs": [], "loose": []}
    assert plan(local, {}, set())["uploads"] == sorted(local)  # first deployment: everything
    assert delete_guard(0, 0) == MIN_DELETE_GUARD and delete_guard(0, 49000) == 12250
    print("deploy.py self-test: OK")
    return 0


def summary(lines: list[str]) -> None:
    text = "\n".join(lines)
    print(text, flush=True)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def listed(items: list[str], fmt: str) -> list[str]:
    out = [fmt.format(i) for i in items[:LIST_LIMIT]]
    if len(items) > LIST_LIMIT:
        out.append(f"- ... and {len(items) - LIST_LIMIT} more")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="show the plan, change nothing")
    ap.add_argument("--allow-mass-delete", action="store_true",
                    help="disable the guard on the number of deletions")
    ap.add_argument("--force-purge", action="store_true", help="purge even without changes")
    ap.add_argument("--workers", type=int, default=24, help="parallel uploads (default 24)")
    ap.add_argument("--local-check", action="store_true",
                    help="run the checks and show the local manifest, without network or secret")
    ap.add_argument("--self-test", action="store_true", help="unit test of the diff logic, then exit")
    args = ap.parse_args()
    if args.self_test:
        return self_test()

    cfg = bunny.site_config()
    files = local_manifest()
    if len(files) <= len(EXTRA_FILES):
        sys.exit("site/ is empty: run python3 -I scripts/build.py first.")
    t0 = time.time()
    sums = checksums(files, 8)
    size = sum(p.stat().st_size for p in files.values())
    print(f"{len(files)} local files, {size / 1e6:.0f} MB, hashed in {time.time() - t0:.0f} s.", flush=True)
    ensure_checks(fingerprint(sums))
    if args.local_check:
        print(f"Local check OK: {len(files)} files would be compared with storage zone {cfg['storage_zone']}.")
        return 0

    storage = bunny.Storage(cfg["storage_zone"])
    t0 = time.time()
    remote, remote_dirs = storage.list_recursive()
    print(f"{len(remote)} remote files in {len(remote_dirs)} folders, listed in {time.time() - t0:.0f} s.", flush=True)
    p = plan(sums, remote, remote_dirs)
    uploads, orphans, orphan_dirs, loose = p["uploads"], p["orphans"], p["orphan_dirs"], p["loose"]

    guard = delete_guard(len(orphans), len(remote))
    if len(orphans) > guard and not args.allow_mass_delete:
        summary([f"**Aborted**: {len(orphans)} deletions planned (> {guard}).",
                 *listed(orphans, "- `{}`"),
                 "Run again with --allow-mass-delete if this is intended."])
        return 2

    label = os.environ.get("DEPLOY_ENV")
    title = ("bunny.net deployment of " + cfg["hostname"] + (f" ({label})" if label else "")
             + (" (dry run)" if args.dry_run else ""))
    lines = [f"## {title}", "",
             f"- {len(files)} local files, {len(remote)} remote files",
             f"- Files to upload: **{len(uploads)}** ({sum(1 for u in uploads if u not in remote)} new)",
             f"- Files to delete: **{len(orphans)}**", ""]
    lines += listed(uploads, "- upload `{}`")
    lines += [f"- delete `{d}/` (folder)" for d in orphan_dirs]
    lines += listed(loose, "- delete `{}`")
    summary(lines)
    if args.dry_run:
        return 0

    done, failed, lock = [0], [], threading.Lock()
    t0 = time.time()

    def upload(rel: str) -> None:
        try:
            storage.upload(rel, files[rel].read_bytes(), sums[rel])
        except RuntimeError as e:
            with lock:
                failed.append(f"{rel}: {e}")
            return
        with lock:
            done[0] += 1
            if done[0] % 1000 == 0:
                print(f"  {done[0]}/{len(uploads)} uploaded ({time.time() - t0:.0f} s)", flush=True)

    with ThreadPoolExecutor(max(1, args.workers)) as pool:
        list(pool.map(upload, uploads))
    print(f"{done[0]} file(s) uploaded in {time.time() - t0:.0f} s.", flush=True)

    if failed:
        print(f"{len(failed)} upload(s) failed (nothing deleted); run again to send only what is missing:")
        print("\n".join(failed[:LIST_LIMIT]))
    else:
        with ThreadPoolExecutor(8) as pool:
            list(pool.map(storage.delete, loose))
        for d in orphan_dirs:
            storage.delete(d + "/")
        print("Storage zone up to date.")

    if done[0] or (orphans and not failed) or args.force_purge:
        bunny.purge_pullzone(bunny.pullzone(cfg["pullzone"])["Id"])
        print("Pull zone cache purged.")
    else:
        print("No change: no purge.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
