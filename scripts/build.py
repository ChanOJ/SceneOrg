#!/usr/bin/env python3
"""Build site/ from the id3 skin z/scene.org (www.scene.org home, 2000-09..2000-11).

Stdlib only, deterministic (no timestamps, sorted walks). The skin is plain HTML apart from the
OJ oneliner on index.htm and the FTP search on search.html; both are rendered/frozen here.
Reads $ID3X_RAW (default ~/Code/id3x/raw); only public oneliner columns are ever selected.
"""
import html
import json
import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("ID3X_RAW", Path.home() / "Code/id3x/raw"))
SKIN = RAW / "id3/z/scene.org"
DB = RAW / "db/OJUICE.sqlite"
SITE = ROOT / "site"
CONF = json.loads((ROOT / "site.json").read_text())
HOST = CONF["hostname"]

# Oneliner window: Scene.org home in the id3 engine, until Orange Juice v3 launched (2000-11-20).
ONELINER_FROM, ONELINER_TO = "2000-09-01", "2000-11-20"
HOME_LINES = 20  # $$BCL:1:20$$ in the skin

# Never published: server-side include, Teleport Pro duplicates of main.html / latest.html
# (their *_files folders are absent), executables (hosting rules), empty files.
SKIP = {"ftpsearch_form.inc", "main.htm", "latest.htm", "index.htm",
        "bank.html",  # bank details and account holder's name of scene.org: no banking data
        "domage/but_modp.gif"}  # button of the ModPlug plugin download, replaced by the player
SKIP_SUFFIX = {".exe", ".inc"}
# Inner pages of domage/index.htm (a frameset): reopened inside it when landed on directly
# (frame-restore.js holds the page -> frame map).
FRAMED = {"domage/" + n for n in ("news.html", "prods.html", "members.html", "links.html", "mod.html")}
# Pages that list people: removal footer.
PEOPLE = {"staff.html", "domage/members.html", "oneliner.html", "index.htm",
          "jobs/spirit.html", "jobs/magnus.html", "jobs/vulpine.html", "its/info.htm"}
# Pages left out of the sitemap (a move notice to a dead host).
NOT_IN_SITEMAP = {"/mono/"}
# Extra files copied from scripts/ into site/ (source, destination).
ASSETS = [("frame-restore.js", "frame-restore.js"), ("mod-player.js", "domage/mod-player.js"),
          ("its.css", "its/its.css")]
VENDOR = "vendor/chiptune"  # chiptune3 (libopenmpt in WebAssembly), copied to site/domage/chiptune/


MAIL = "chandra_oj&#64;pm.me"
FOOTER = ('<p align="center"><font face="Verdana, Arial, Helvetica, sans-serif" size="-2">'
          'To be removed from this page, <a href="mailto:%s">contact me</a>.</font></p>\n' % MAIL)
ARCHIVE_NOTE = ('<p><font face="Arial, Helvetica, sans-serif"><b>Archived page.</b> The file search of '
                'scene.org (2000) was a live database query; it is no longer available. The archive '
                'itself is still at <a href="https://files.scene.org/">files.scene.org</a>.'
                '</font></p>\n')
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def enc(s: str) -> bytes:
    return s.encode("latin-1", "xmlcharrefreplace")


# Targets that are not in the raw copy (empty file, CGI form, executable, missing folder): the link
# becomes plain text followed by a note.
DEAD = ("areyou32.zip", "cgi-bin/webapply.pl.htm", "its.exe", "ptc/index.htm", "bank.html")

# Privacy of the job offers: phone, fax and street address dropped; e-mail whose local part is a
# family name: domain cut. (page, old, new), exact replacements.
JOB_FIXES = [
    ("jobs/spirit.html", '<a href="mailto:hanek@spiritlink.de">Hanek@spiritlink.de</a>', "hanek@????"),
    ("jobs/spirit.html", "e-mail: mailto:hanek@spirit-link.de tel: 09131/8126648<br>", "e-mail: hanek@????<br>"),
    ("jobs/spirit.html", "web : http://www.spirit-link.de fax: 09131/8126657<br>", "web : http://www.spirit-link.de<br>"),
    ("jobs/spirit.html", "----SPIRIT LINK GMBH::AM WEICHSELGARTEN 19::91058 ERLANGEN----", "----SPIRIT LINK GMBH----"),
    # Teleport Pro leftover: the mailto pointed to the home page
    ("jobs/papple.html", '<a\r\nhref="../index.htm">fruitless@pineapple-interactive.com</a>',
     '<a href="mailto:fruitless@pineapple-interactive.com">fruitless@pineapple-interactive.com</a>'),
]

MOD_BODY = ('<BODY BGColor=#000000 text=#C0C0C0 link=#C0C0C0 vlink=#C0C0C0 alink=#FFFFFF>\n<!-- ONLINE MODULE! -->\n'
            '<CENTER>\n<FONT FACE="Verdana, Arial, sans-serif" SIZE="-2">module<br><b id="state">amando.xm</b></FONT><br>\n'
            '<BUTTON id="play" type="button" aria-pressed="false" style="margin-top:4px">Play</BUTTON>\n</CENTER>\n'
            '<script type="module" src="mod-player.js"></script>\n</body>')


def fix_html(rel: str, t: str) -> str:
    t = re.sub(r'\s+tppabs="[^"]*"', "", t)  # Teleport Pro leftovers
    t = re.sub(r"javascript:if\(confirm\('[^']*'\)\)window\.location='([^']*)'", r"\1", t)
    t = t.replace("http://www.scene.org/", "/")
    for d in DEAD:
        t = re.sub(r'<a\s[^>]*href="%s"[^>]*>(.*?)</a>' % re.escape(d), r"\1 <i>(not archived)</i>", t,
                   flags=re.S | re.I)
    for page, old, new in JOB_FIXES:
        if rel == page:
            assert old in t, (page, old)
            t = t.replace(old, new)
    t = re.sub(r'\s*<meta\s+name="author"[^>]*>', "", t, flags=re.I)  # real names of authors, invisible
    t = re.sub(r"<!-- Changed by:[^>]*-->\s*", "", t)  # Dreamweaver trace with a full name
    if rel == "mono/index.htm":
        t = re.sub(r'\s*<meta\s+http-equiv="refresh"[^>]*>', "", t, flags=re.I)  # no automatic leave
    if rel.startswith("its/") and rel.endswith((".htm", ".html")):
        t = re.sub(r"</head>", '<link rel="stylesheet" href="its.css" type="text/css">\n</head>', t, count=1, flags=re.I)
    if rel == "domage/mod.html":
        t, n = re.subn(r"<BODY\b.*</body>", lambda m: MOD_BODY, t, count=1, flags=re.S | re.I)
        assert n == 1
    if rel == "domage/index.htm":
        t = re.sub(r"(<head[^>]*>)", r'\1\n<script src="/frame-restore.js"></script>', t, count=1, flags=re.I)
    if rel == "search.html":
        a = t.index("<form method=\"get\" action=\"search.html\"")
        b = t.index("<!-- #EndEditable -->", a)
        t = t[:a] + ARCHIVE_NOTE + "\t\t\t" + t[b:]
    if rel in FRAMED:
        t = re.sub(r"(<head[^>]*>)", r'\1\n<script src="/frame-restore.js"></script>', t, count=1, flags=re.I)
        # Frames: external links open in a new tab (they would replace the whole window otherwise).
        def blank(m):
            tag = re.sub(r'\s+(?:target|rel)\s*=\s*(?:"[^"]*"|[^\s>]+)', "", m.group(0))
            return tag[:-1] + ' target="_blank" rel="noopener">'
        t = re.sub(r'<a\s[^>]*href\s*=\s*"(?:https?|ftp)://[^"]*"[^>]*>', blank, t, flags=re.I)
    if rel in PEOPLE:
        t = re.sub(r"</body>", lambda m: FOOTER + "</body>", t, count=1, flags=re.I)
    return t


def oneliner_rows(limit=None):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    q = ("SELECT dt, nick, sentence FROM ONELINER WHERE dt >= ? AND dt < ? "
         "ORDER BY dt DESC, id DESC" + (f" LIMIT {int(limit)}" if limit else ""))
    rows = con.execute(q, (ONELINER_FROM, ONELINER_TO)).fetchall()
    con.close()
    return rows


def clean(s: str) -> str:
    return html.escape(EMAIL.sub(lambda m: m.group().split("@")[0] + "@????", s or "").strip())


def render_index() -> str:
    t = (SKIN / "index.htm").read_bytes().decode("latin-1").replace("\r\n", "\n")
    t = re.sub(r"<SCRIPT language=\"JavaScript\"><!--\nfunction popup.*?</SCRIPT>\n", "", t, count=1, flags=re.S)
    lines = "".join('%s:%s %s<BR>\n' % (r[0][11:13], r[0][14:16], clean(r[2])) for r in oneliner_rows(HOME_LINES))
    box = ('<TABLE width="640" cellpadding=2 class=specialtable>\n\t\t<TR> \n\t\t\t<TD class=smtxt>\n%s'
           '<BR><A href="oneliner.html">older lines</A>\n\t\t\t</TD>\n\t\t</TR>\n\t</TABLE>\n' % lines)
    t = re.sub(r"<FORM action.*?</FORM>\n", lambda m: box, t, count=1, flags=re.S)
    t = re.sub(r"\t\t\t<SCRIPT language=\"JavaScript\">\n.*?</SCRIPT>\n\t\t\t<CENTER>.*?</CENTER>\n", "", t, count=1, flags=re.S)
    t = t.replace('<A href="main.html">', '<A href="main.html">', 1)
    return fix_html("index.htm", t)


def render_oneliner() -> str:
    rows = []
    for dt, nick, sentence in oneliner_rows():
        who = "<b>%s</b> " % html.escape(nick.strip()) if nick and nick.strip() else ""
        rows.append("%s %s%s<BR>" % (dt[:16], who, clean(sentence)))
    t = ('<html>\n<head>\n<title>Scene.org - oneliner archive</title>\n'
         '<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">\n'
         '<link rel="stylesheet" href="sceneorg.css" type="text/css">\n</head>\n'
         '<body bgcolor="#FFFFFF" text="#000000" link="#339900" vlink="#006600" alink="#009900">\n'
         '<p align="center"><a href="index.htm"><img src="images/sceneorg_logobig.jpg" width="564" height="258" border="0" alt="scene.org"></a></p>\n'
         '<table width="640" cellpadding=2 align="center" class=specialtable><tr><td class=smtxt>\n'
         '<p><b>Oneliner</b>, %s to %s: %d lines, newest first (archived, the form is gone).</p>\n%s\n'
         '</td></tr></table>\n</body>\n</html>\n') % (ONELINER_FROM, "2000-11-19", len(rows), "\n".join(rows))
    return fix_html("oneliner.html", t)


def build() -> list[str]:
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    out: dict[str, bytes] = {}
    for p in sorted(SKIN.rglob("*")):
        if not p.is_file() or p.name == ".DS_Store":
            continue
        rel = p.relative_to(SKIN).as_posix()
        if rel in SKIP or p.suffix.lower() in SKIP_SUFFIX or p.stat().st_size == 0:
            continue
        data = p.read_bytes()
        if p.suffix.lower() in (".htm", ".html"):
            data = enc(fix_html(rel, data.decode("latin-1")))
        out[rel] = data
    out["index.htm"] = enc(render_index())
    out["oneliner.html"] = enc(render_oneliner())
    for src, dst in ASSETS:
        out[dst] = (ROOT / "scripts" / src).read_bytes()
    for f in sorted((ROOT / "scripts" / VENDOR).iterdir()):
        out["domage/chiptune/" + f.name] = f.read_bytes()
    for rel in [r for r in out if r.endswith("/index.htm") or r == "index.htm"]:
        out[rel + "l"] = out[rel]  # bunny storage serves index.html for directories
    out["404.html"] = (ROOT / "hosting/404.html").read_bytes()
    out["robots.txt"] = ("User-agent: *\nAllow: /\n\nSitemap: https://%s/sitemap.xml\n" % HOST).encode()
    pages = sorted(r for r in out if r.endswith((".htm", ".html")) and r != "404.html"
                   and not (r.endswith("/index.htm") or r == "index.htm"))
    urls = ["/"] + ["/" + r[:-len("index.html")] if r.endswith("index.html") and "/" in r else "/" + r
                    for r in pages if r != "index.html"]
    urls = sorted(set(urls) - NOT_IN_SITEMAP)
    out["sitemap.xml"] = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                          + "".join("<url><loc>https://%s%s</loc></url>\n" % (HOST, u) for u in urls)
                          + "</urlset>\n").encode()
    for rel, data in sorted(out.items()):
        dest = SITE / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return sorted(out)


if __name__ == "__main__":
    files = build()
    print(f"site/: {len(files)} files")
