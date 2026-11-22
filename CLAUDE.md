# CLAUDE.md

Guidance for Claude Code in this repository. Maintainer documentation is in
[docs/maintaining.md](docs/maintaining.md); read it before changing the build.

## What this is

The build for the French vACC's NeoRadar package, `LFXX`: all of France in one package, built from
the military GNG sector file (`LFFM`), which covers every French FIR. NeoRadar serves approach and
below for now: centre ASRs are left out. It holds scripts and settings only. The package is
rebuilt from upstream on each run:

- `vaccfr/Sector-Files` (public): ASRs, login profiles, aliases
- `alexisBalzano/CoFrance-config-files` (public): CoFrance maps (its `tag_formats.json` is the
  reference the two systems were ported from, not a build input)
- `vaccfr/data-sectorfiles` (PRIVATE): GNG `.sct`/`.ese`, ICAO, NavData

Laid over each other, they form a "source tree" with the French Controller Pack layout. A local
Controller Pack install (e.g. `~/Documents/FrenchVACC`) is already one.

## Hard rules

- **Never commit or publish restricted data**: `.sct`, `.ese`, built packages (`build/`, `dist/`,
  zips), `server-dataset.json`, `airways.db`. Never copy anything from `data-sectorfiles` into
  this repo. The Validate workflow fails on them.
- **Never edit `build/` to fix something.** It is regenerated from scratch. Fix the script, the
  shared files, or upstream.
- **Prefer upstream fixes.** Wrong ASRs, maps or positions are wrong in EuroScope too. Report
  them; only work around them in the build (with a warning) when they break NeoRadar.
- **Every build warning must say what is wrong and where to fix it.** Do not drop data silently.
- **Validate before you finish**: build, then `node scripts/validate.js <schemas@main> build/*/package`
  must pass.
- Commit and push only when the maintainer asks, and to where they say (they may want it
  straight on `main`).

## Layout

| Path | What |
| --- | --- |
| `packages.json` | The package: id, namespace (permanent: provider URL and server vAcc id), sector file, FIR folders, `excludeAsrs` and `excludeLoginFacilities` (centre displays and logins left out), ICAO/NavData folder, publish settings |
| `scripts/build.py` | `assemble` (source tree → `build/<ID>/` environment) and `finalize` (after `neoradar-cli convert`: profiles, manifest) |
| `scripts/cofrance.py` | CoFrance GeoJSON maps → NeoRadar map layers (EPSG:3857, item table, `showWhen` from CoFrance `activation`) |
| `scripts/build-all.sh` | assemble → convert → finalize for all or some packages; CI and local both use it |
| `scripts/validate.js` | Schema check of built packages (ajv), plus every `=rule`, `$expression`, shape and `#system` reference in the systems |
| `shared/package/` | Copied into every package: systems, fonts, images, sounds |
| `shared/package/systems/` | The two static systems: `neoirma` (stripless IRMA: every approach but CDG, and the one ground look, used by every AVISO) and `cdg` (Paris-CDG approach; its ground is `#neoirma`). Tracks are vector shapes in `shapes.json` |
| `backup/` | The systems, sprite atlas and tag-format generator before the two-system cleanup. Not built, kept for reference |
| `diffs/`, `transforms/` | Patches and text replacements applied to source files during `assemble` |
| `.github/workflows/` | `release.yml` (build, validate, publish), `validate.yml` (repo checks) |

## Commands

```bash
scripts/build-all.sh ~/Documents/FrenchVACC [LFXX]               # needs neoradar-cli on PATH, or NEORADAR_CLI="node <cli>/dist/index.js"
python scripts/build.py assemble --source <tree> [--only IDS]
python scripts/build.py finalize [--only IDS]
node scripts/validate.js <schemas checkout> build/*/package      # ajv@8 + js-yaml@4 resolvable
```

## Things that are easy to get wrong

- **neoradar-cli and the schemas run from `main`.** CI pins both through `NEORADAR_CLI_REF` /
  `NEORADAR_SCHEMAS_REF` in `release.yml`.
- **Publishing goes to Cloudflare R2** (`publish` in `packages.json`: bucket `neoradar-packages`,
  path `lfxx`, served at `https://pkg.neoradar.app/lfxx`). The keys are the repository secrets
  `NEORADAR_R2_ACCESS_KEY_ID` / `NEORADAR_R2_SECRET_ACCESS_KEY`; never put them in a file.
- **The client is the arbiter, the schemas describe it.** The C# client is
  `neoradar-project/client-sharp` (`develop`); check it when a field's behaviour matters. A field
  that validates can still mean something new (e.g. a style variant without `leaderLineColor`
  draws no leader line; truncate `"0,0"` no longer hides an item, use the item's `applyWhen`).
- **Profiles need an explicit `atmSystem`.** Without one the client falls back to the first
  system alphabetically (`cdg`). `finalize` sets one on every profile.
- **A profile with an empty item list draws every layer.** `finalize` fills AVISO profiles, whose
  upstream ASRs carry no map content on purpose.
- **Two systems, edited by hand.** The build does not read CoFrance's tag formats: a CoFrance
  colour or rule change is ported into `shared/package/systems` by hand. Track colours follow
  CoFrance's IRMA / Paris-CDG rules in priority order; the flight state is the callsign's reverse
  video (docs/maintaining.md has the table).
- **Filtered traffic is hidden unless a variant lists its filter state.** Variants for flows
  CoFrance never filters, and for flights assumed or in transfer, list all `applyToFilterStates`;
  tag layouts have a twin keyed on `$<system>ThroughFilter`. Keep targets, styles and layouts in
  step.
- **Shapes fill axis-aligned rects and full circles in the client** (circles from client-sharp
  develop `7a39b6c4f`). Any other polygon with `fill` draws as an outline.
- **The server's data is separate.** `server-dataset.json` is uploaded with
  `neoradar-cli push-dataset`; procedure rules and runway preferences are server config, not
  part of the package.
- Source files are partly Windows-1252 with CRLF: `read_text_any` decodes and normalises them.
  Sector files are copied byte for byte.

## Related repos

`neoradar-project/cli` (the converter), `neoradar-project/schemas` (file formats),
`neoradar-project/client-sharp` (the client), `neoradar-project/neoradar-server`. Problems in
those are reported there, not worked around silently here.
