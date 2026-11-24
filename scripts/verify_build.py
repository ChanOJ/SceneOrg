#!/usr/bin/env python3
"""Checks on site/: no leftover macro or form, local links resolve, footers, frames, oneliner
window, no private data, nothing from the exclude list. With --rebuild (local only, needs the
raw store): the committed site/ equals a fresh build, i.e. the build is deterministic."""
import fnmatch
import hashlib
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
errors: list[str] = []


def err(msg):
    errors.append(msg)


def digest():
    h = hashlib.sha256()
    for p in sorted(SITE.rglob("*")):
        if p.is_file() and p.name != ".DS_Store":
            h.update(p.relative_to(SITE).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


def main():
    files = {p.relative_to(SITE).as_posix() for p in SITE.rglob("*") if p.is_file() and p.name != ".DS_Store"}
    globs = [l.strip() for l in (ROOT / "scripts/exclude-globs.txt").read_text().splitlines()
             if l.strip() and not l.startswith("#")]
    for f in sorted(files):
        for g in globs:
            if fnmatch.fnmatch(f, g) or ("/" not in g and fnmatch.fnmatch(f.rsplit("/", 1)[-1], g)):
                err(f"excluded file published: {f}")
    for must in ("index.htm", "index.html", "main.html", "oneliner.html", "robots.txt", "sitemap.xml", "404.html",
                 "domage/index.html", "its/index.html"):
        if must not in files:
            err(f"missing {must}")
    for f in sorted(files):
        if not f.endswith((".htm", ".html")):
            continue
        t = (SITE / f).read_bytes().decode("latin-1")
        for bad in ("$$", "<form", "<FORM", "tppabs", "javascript:if(confirm", "ojuice.net/oneliner_popup", "ftpsearch"):
            if bad in t:
                err(f"{f}: contains {bad!r}")
        if re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", t) and f in ("oneliner.html", "index.htm"):
            err(f"{f}: IP-like text")
        if f in ("staff.html", "domage/members.html", "oneliner.html", "index.htm") and "To be removed from this page" not in t:
            err(f"{f}: missing removal footer")
        if f.startswith("domage/") and f not in ("domage/index.htm", "domage/index.html", "domage/niks.html") \
                and "window.top===window" not in t:
            err(f"{f}: not reopened in its frameset")
        for m in re.finditer(r"""(?:href|src|background)\s*=\s*["']?([^"' >]+)""", t, flags=re.I):
            u = m.group(1)
            if u.startswith(("#", "mailto:", "http:", "https:", "ftp:", "news:", "javascript:")):
                continue
            path = urlparse(u).path
            base = SITE / f if path.startswith("/") is False else SITE
            target = (SITE / path.lstrip("/")) if path.startswith("/") else (SITE / f).parent / path
            try:
                rel = target.resolve().relative_to(SITE.resolve()).as_posix()
            except ValueError:
                err(f"{f}: link outside site: {u}")
                continue
            if rel in (".", ""):
                continue
            if rel not in files and (rel.rstrip("/") + "/index.html" not in files) and rel != "":
                err(f"{f}: broken link {u}")
    o = (SITE / "oneliner.html").read_bytes().decode("latin-1")
    dates = re.findall(r"^(\d{4}-\d{2}-\d{2}) \d\d:\d\d ", o, flags=re.M)
    if not dates or min(dates) < "2000-09-01" or max(dates) >= "2000-11-20":
        err(f"oneliner outside window: {min(dates, default=None)}..{max(dates, default=None)}")
    if re.search(r"[\w.+-]+@(?!\?\?\?\?)[\w-]+\.\w+", o):
        err("oneliner: e-mail address left")
    if "--rebuild" in sys.argv:  # needs the raw store (local only): site/ must equal a fresh build
        first = digest()
        subprocess.run([sys.executable, "-I", str(ROOT / "scripts/build.py")], check=True, stdout=subprocess.DEVNULL)
        if digest() != first:
            err("build is not deterministic: site/ differs from a fresh build")
    for e in errors:
        print("ERROR", e)
    print(f"{len(files)} files checked, {len(errors)} error(s)")
    return 1 if errors else 0


sys.exit(main())
