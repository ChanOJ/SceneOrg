# SceneOrg

Static, read-only archive of the **Scene.org home site as served by the id3 engine** (September to
November 2000, 116 files), kept online at https://sceneorg.sauthier.family. Part of the old sites
published by [ChanOJ](https://chanoj.github.io).

Scene.org was the demoscene's file archive and portal. In late 2000 a copy of its home pages (news,
services, staff, sponsors, viewing tips, FTP search form, job offers) ran on id3, the in-house ASP
multi-site engine behind [Orange Juice](https://orangejuicev3.sauthier.family); the only dynamic
part was the Orange Juice oneliner on the front page.

## What is in the archive

- The pages, images and CSS of the skin, unchanged apart from the cleanups below.
- `domage/` (a demogroup's pages hosted on scene.org, a frameset: inner pages reopen inside it when
  landed on directly), `its/` (Impact Texture Studio, a texture tool; the .exe is not published), `jobs/`, `mono/` (a move notice).
- **Oneliner**: the front page shows the last 20 lines as of 2000-11-19; `oneliner.html` holds the
  whole period (2000-09-01 to 2000-11-19, nicks only, no IP, host or user agent; e-mail
  addresses cut to `local@????`).
- The FTP search form was a live database query: replaced by an "archived" notice.
- Pages listing people (staff, group members, oneliner) end with a removal contact line.
- Dropped: the forms, the Teleport Pro duplicates `main.htm` / `latest.htm`, the server-side
  include, `its.exe`, an empty `areyou32.zip` and two dead targets (shown as "not archived").

The engine code is never published.

## Build and deploy

Inputs come only from the shared raw store `~/Code/id3x/raw` (`$ID3X_RAW`): the skin
`id3/z/scene.org` and, for the oneliner only, `db/OJUICE.sqlite` (private, never copied here).

```bash
python3 -I scripts/build.py          # site/ (git-ignored), deterministic
python3 -I scripts/verify_build.py   # checks + builds a second time and compares hashes
python3 -I scripts/check_excludes.py # nothing from scripts/exclude-globs.txt in site/
scripts/publish.sh                   # build, verify, deploy to bunny.net, smoke test
```

`site/` is generated on the Mac because the oneliner needs the private database; CI only plans and
applies `infra/` and runs the weekly smoke test. Hosting is the same as
[OrangeJuiceV3](https://github.com/ChanOJ/OrangeJuiceV3): OpenTofu (`infra/`, encrypted state),
bunny.net storage zone + pull zone `sceneorg`, no edge script (no old query-string URL to map).
One-time setup: `scripts/bootstrap.sh`.
