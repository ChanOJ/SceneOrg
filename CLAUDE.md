# SceneOrg: context for Claude sessions

Static archive of the Scene.org home site served by the id3 engine (2000-09 to 2000-11). Public
repo `ChanOJ/SceneOrg`, hostname `sceneorg.sauthier.family`, bunny storage and pull zone `sceneorg`,
Proton Pass item `SceneOrg-tofu-state-passphrase` (vault `OldSites`). Template: `~/Code/OrangeJuiceV3`;
family context: `~/Code/id3x/CLAUDE.md`.

## Hard rules

- Inputs only from the raw store `~/Code/id3x/raw` (skin `id3/z/scene.org`, oneliner from
  `db/OJUICE.sqlite`). The database holds IPs, hosts, user agents: `scripts/build.py` selects only
  `dt, nick, sentence`; keep it that way.
- Never publish engine code or `*.exe` (see `scripts/exclude-globs.txt`).
- Pages that list people keep the footer "To be removed from this page, contact me."
- `site/` is generated and git-ignored; build twice, same hashes (`scripts/verify_build.py`).
