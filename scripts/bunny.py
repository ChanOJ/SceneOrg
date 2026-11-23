"""bunny.net helpers shared by the scripts (standard library only, Python >= 3.9).

The site settings come from site.json (repository root); the files served come from site/
(generated on the Mac by scripts/build.py, not committed) and hosting/. The only secret is the
account API key (BUNNY_API_KEY or BUNNYNET_API_KEY): the storage zone password
and the pull zone id are looked up from it, so they are never stored anywhere.
"""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = REPO_ROOT / "site"  # generated static site (scripts/build.py), git-ignored
HOSTING_DIR = REPO_ROOT / "hosting"  # files owned by the hosting setup (404 page)
API = "https://api.bunny.net"
RETRIES = 4


def site_config() -> dict:
    return json.loads((REPO_ROOT / "site.json").read_text())


def api_key() -> str:
    key = os.environ.get("BUNNY_API_KEY") or os.environ.get("BUNNYNET_API_KEY")
    if not key:
        sys.exit("Missing environment variable BUNNY_API_KEY (bunny.net account API key).")
    return key


def request(method: str, url: str, headers: dict, data: bytes | None = None) -> bytes:
    """HTTP request with retries on network errors and 5xx answers."""
    for attempt in range(1, RETRIES + 1):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            if (e.code < 500 and e.code != 429) or attempt == RETRIES:
                raise RuntimeError(f"{method} {url} -> HTTP {e.code}: {body}") from None
        except urllib.error.URLError as e:
            if attempt == RETRIES:
                raise RuntimeError(f"{method} {url} -> {e.reason}") from None
        time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def api_get(path: str) -> object:
    return json.loads(request("GET", API + path, {"AccessKey": api_key(), "Accept": "application/json"}))


def storage_zone(name: str) -> dict:
    zones = api_get("/storagezone?perPage=1000&search=" + urllib.parse.quote(name))
    for z in zones:
        if z["Name"] == name and not z.get("Deleted"):
            return z
    sys.exit(f"Storage zone {name!r} not found.")


def pullzone(name: str) -> dict:
    zones = api_get("/pullzone?perPage=1000&search=" + urllib.parse.quote(name))
    items = zones["Items"] if isinstance(zones, dict) else zones
    for z in items:
        if z["Name"] == name:
            return z
    sys.exit(f"Pull zone {name!r} not found.")


def purge_pullzone(pullzone_id: int) -> None:
    request("POST", f"{API}/pullzone/{pullzone_id}/purgeCache", {"AccessKey": api_key()}, b"")


class Storage:
    """Storage zone file API (password looked up from the account API key)."""

    def __init__(self, zone_name: str):
        zone = storage_zone(zone_name)
        host = zone.get("StorageHostname") or "storage.bunnycdn.com"
        self.base = f"https://{host}/{urllib.parse.quote(zone_name)}/"
        self.headers = {"AccessKey": zone["Password"]}

    def _url(self, rel: str) -> str:
        return self.base + urllib.parse.quote(rel, safe="/")

    def list_dir(self, d: str) -> list[dict]:
        return json.loads(request("GET", self._url(d), self.headers) or b"[]")

    def list_recursive(self, workers: int = 16) -> tuple[dict[str, str | None], set[str]]:
        """Return ({file_path: SHA-256 checksum}, {directory_paths}), listing folders in parallel."""
        files: dict[str, str | None] = {}
        dirs: set[str] = set()
        level = [""]
        with ThreadPoolExecutor(workers) as pool:
            while level:
                nxt = []
                for d, entries in zip(level, pool.map(self.list_dir, level)):
                    for e in entries:
                        rel = d + e["ObjectName"]
                        if e["IsDirectory"]:
                            dirs.add(rel)
                            nxt.append(rel + "/")
                        else:
                            checksum = e.get("Checksum")
                            files[rel] = checksum.upper() if checksum else None
                level = nxt
        return files, dirs

    def download(self, rel: str) -> bytes:
        return request("GET", self._url(rel), self.headers)

    def upload(self, rel: str, data: bytes, checksum: str) -> None:
        request("PUT", self._url(rel), {**self.headers, "Content-Type": "application/octet-stream",
                                        "Checksum": checksum}, data)

    def delete(self, rel: str) -> None:
        request("DELETE", self._url(rel), self.headers)
