# Maintaining the French NeoRadar packages

This repo turns the French vACC's EuroScope Controller Pack into one NeoRadar package, `LFXX`. It holds
only scripts and settings: every build starts from the upstream sources, so most changes belong
upstream, and a release is mostly "update the data, run the workflow".

## How it fits together

```text
vaccfr/Sector-Files (public)              ASRs, login profiles, aliases
alexisBalzano/CoFrance-config-files       CoFrance maps
vaccfr/data-sectorfiles (PRIVATE)         GNG sector files, ICAO
                │
                ▼  laid over each other into one "source tree"
   scripts/build.py assemble   → build/<ID>/        one neoradar-cli environment per package
   neoradar-cli convert        → build/<ID>/package the converted package
   scripts/build.py finalize   → profiles finished, manifest cleaned
   scripts/validate.js         → checked against the NeoRadar schemas
   neoradar-cli distribute     → zip + publish to the R2 bucket, served at pkg.neoradar.app
```

`scripts/build-all.sh` runs the first three steps; the **Publish Release** workflow runs them all.

| Package | Built from | FIR folders |
| --- | --- | --- |
| `LFXX` | `LFXX/Sectors/LFFM.sct/.ese` (the military GNG file, all French FIRs) | LFFF, LFEE, LFRR, LFBB, LFMM, LFFM |

It is defined in `packages.json`. ASRs, login profiles and CoFrance maps come from every FIR folder
listed (the first FIR wins a duplicated callsign); ICAO comes from `LFFM` (`dataFolder`).
The per-FIR GNG files (`LFBB`, `LFFF`, `LFEE`, `LFMM`, `LFRR`) are no longer used, and
`data-sectorfiles` no longer carries them.

NeoRadar is used for approach and below for now, so the centre displays are left out:
`excludeAsrs` in `packages.json` lists them as globs (`* FIR.asr`, `* UIR.asr`, `* CTR.asr`; and
`* Legacy APP.asr`, the old approach displays the CoFrance ones replace), and
the build log names every ASR it skipped. The centre login profiles go too: `excludeLoginFacilities`
lists EuroScope facility numbers (`6` is centre). Remove a pattern to ship those displays again (they
would then need a system: see below).

## Each AIRAC

1. Download the France Military (`LFFM`) package from GNG.
2. Copy it into your clone of `vaccfr/data-sectorfiles` (its README has the exact steps):
   - `LFXX/Sectors/`: the military file renamed `LFFM.sct` / `LFFM.ese`, and `current_airac.txt`
   - `LFFM/ICAO/`

   Copy nothing else: anything else in that repo overrides the public Sector-Files copy.
3. Commit as the AIRAC (e.g. `2612`) and push.
4. Run **Publish Release** (below).
5. Upload the server datasets (below).

## Releasing

GitHub → Actions → **Publish Release** → Run workflow.

- **packages**: leave empty (there is only `LFXX`).
- **revision**: 1 for the first release of an AIRAC, then 2, 3… (the version is `<AIRAC>.<revision>`).
- **publish**: untick to only build. The zips are then in the run's artifacts, to try first.

The package goes to the Cloudflare R2 bucket `neoradar-packages` under `lfxx/`, which
`https://pkg.neoradar.app/lfxx` serves (the provider URL controllers add). `publish` in
`packages.json` holds the bucket, endpoint and the names of the two key variables; the keys
themselves are repository secrets (below).

The run fails on a missing input, a convert error or a schema error, before anything is
published. It also fails if publishing was asked for and the R2 secrets are missing, or if
`neoradar-cli distribute` does not report the package published. Read its warnings either way (see [Build warnings](#build-warnings)).

Record what each release changes in `changelog/<AIRAC>.txt` (one file per AIRAC, a line per
revision), and batch changes into a release rather than publishing each one.

Versions are `<AIRAC>.<revision>`, e.g. `2611.1`: **revision** is a workflow input, 1 for the first
release of a cycle. To republish within the same AIRAC, run it again with the next revision
(`2611.2`). The client offers an update whenever the published version differs from the
installed one, so never reuse a version for different content.

### Server datasets

Each build also writes `build/<ID>/server-dataset.json` (procedures, positions, sectors,
navaids). The NeoRadar server needs it for routes, procedures and runway suggestions. It is in the
run's `server-artifacts-<sha>` artifact. Upload each one with a staff token:

```bash
NEORADAR_STAFF_TOKEN=... neoradar-cli push-dataset --vacc lfxx --server https://<server> build/LFXX/server-dataset.json
```

It stages the file, shows what changes on the server and publishes only after you type the vAcc id
(`--stage-only` stops after the review). The vAcc id is the package namespace. A local build from
the same sources gives the same file as CI, which copies it straight out of the build.

## Building locally

You need Python 3.10+, Node 24, pnpm 10, and neoradar-cli from its `main` branch:

```bash
pnpm add -g "github:neoradar-project/cli#main"
```

Build from your Controller Pack folder (it already has everything laid out):

```bash
scripts/build-all.sh ~/Documents/FrenchVACC
```

To try a package in NeoRadar, link it into the packages folder (Windows, PowerShell):

```powershell
New-Item -ItemType Junction -Path "$env:USERPROFILE\Documents\NeoRadar\packages\LFXX" `
  -Target "$PWD\build\LFXX\package"
```

Close NeoRadar before rebuilding: the build deletes and recreates `build/<ID>`.

To check against the schemas:

```bash
npm install --no-save --prefix scripts ajv@8 js-yaml@4
git clone https://github.com/neoradar-project/schemas ../schemas
node scripts/validate.js ../schemas build/*/package
```

## Making changes

**Fix it upstream when you can.** A wrong ASR, map or position is wrong in EuroScope too. Fix it
in Sector-Files or CoFrance-config-files and it reaches the next build. Use the options below
only for what is NeoRadar-specific or cannot wait.

### Tag colours, labels, symbols (radar systems)

There are three systems, all static files in `shared/package/systems/`, edited by hand. The build
no longer reads CoFrance's `tag_formats.json`: when CoFrance changes a colour or rule, port it here.

| System | Used by | Track logic from |
| --- | --- | --- |
| `neoirma` | every CoFrance approach display except Paris-CDG and Paris-Orly, and every other AVISO (ground) display | CoFrance tag format `IRMA` |
| `cdg` | the Paris-CDG approach (`PLUGIN:CoFrance:TagFormat:Paris-CDG`), and the LFPG and LFPB AVISOs (`SYSTEM_FOR_AVISO`) | CoFrance tag format `Paris-CDG` |
| `orly` | the Paris-Orly approach (`PLUGIN:CoFrance:TagFormat:Paris-Orly`, the EGA Paris-Orly display), and the LFPO AVISO (`SYSTEM_FOR_AVISO`) | CoFrance tag format `Paris-Orly` |

`SYSTEM_FOR_TAG_FORMAT` in `scripts/build.py` maps tag formats to systems; anything else gets
`neoirma`. neoIRMA is a stripless IRMA, not the real-world one. Its `ground` section (labels and
targets) is the package's only ground look: the AVISO look, raw video with a small ring. `cdg`'s
and `orly`'s `ground` and `groundSymbology` are `"#neoirma"`, a reference to it.

`orly` is neoIRMA with Paris-Orly's flows: its tags, tag positioning, track triangle, trails,
`mapstyle.yaml` and `policy.json` are neoIRMA's, copied (the CoFrance Orly display differs from the
other approach displays only by its maps and tag format). Only the track and style variants differ.
A change to neoIRMA's tags, mapstyle or safety nets is made in `orly` too.

**Track colours** follow the CoFrance rules in their priority order (the first matching variant
wins, as CoFrance's lowest priority number does):

- `neoirma`: departures pink `#D597A3`, arrivals blue `#63BBD9`, everything else a quiet grey
  `#8E8E8E`. Departure and arrival are NeoRadar's `isDeparture` / `isArrival`: the plan leaves
  from or lands at an airport the controller has active (with runways set), not CoFrance's
  "any `LF*` airport".
- `cdg`: CoFrance's Paris-CDG letters and colours: `S`/`N` CDG arrivals by runway pair (the
  assigned arrival runway, or the server's suggestion while none is assigned), `B` Le Bourget,
  `O` Orly, `A` Pontoise/Beauvais, `V` Toussus/Villacoublay, `R` CDG with no runway yet, `G`/`P`
  local flights, two-letter departure codes by route point (`NN` NURMO, `EL` LANVI…), `T` other
  Paris departures, black `Z` (VFR) and `X` (the rest).
- `orly`: CoFrance's Paris-Orly letters (at the leader base, as `cdg`) and colours: `P` local
  flights within Orly / Toussus / Villacoublay `#D1D5D0`, `O` Orly arrivals `#F8A29A`, `V`
  Toussus / Villacoublay arrivals `#E7A3FA`, `K` Le Bourget arrivals `#4CBC38`, `G` CDG arrivals
  and `E` CDG / Le Bourget departures `#C6B68F`, `M` Orly / Toussus / Villacoublay departures
  `#ACE2DD`, `S` VFR `#ACAFAB` and `X` the rest `#93886F`. `S` and `X` are altitude-filtered, as
  in CoFrance; the others show through the filter.

**Altitude filter.** CoFrance shows flights from a rule with `filtered: false`, and any flight
assumed by you, in transfer to or from you, through the altitude filter. Each variant that does
this lists every `applyToFilterStates`; the tag layouts have a twin keyed on
`$neoirmaThroughFilter` / `$cdgThroughFilter` for the same flights.

**Flight state** is on the callsign. CoFrance's IRMA and Paris-CDG formats colour by flow, not
by state, so the state is shown in reverse video, the same in every system whatever the flow
(the `assumed…`, `incomingTransfer…` and `handoffText` rules in `expressions.json`):

| State | Callsign |
| --- | --- |
| Assumed | white `242,244,247` on a dark slate plate `30,38,46` |
| Transfer to you | CoFrance's hand-off green `160,216,180` on the same plate |
| Transferred out | hand-off green text, no box |
| Other | the track colour, no box |

The callsign is two items: with its plate (`$hasCallsignBox`) it has `padding: [1, 3]` so the
plate does not sit hard against the glyphs; without one (`$hasNoCallsignBox`) `[1, 0]`, so it
lines up with the other rows. The detailed airborne tags show the voice type after it as `/v`,
`/r` or `/t` (the compact ones only `/r` and `/t`), so the voice-type menu is always a click away.
Boxes in the track colour were hard to tell apart from the map and from each other; one plate
per state, darker than the map, reads at a glance.

Track symbols are vector shapes (`shapes.json`), coloured by each variant's `plotColor`, not
sprites. CDG's flow letters (`S`, `NN`…) are text at the base of the leader line, as at Paris-CDG:
the plot is the bare disc (`cdg/track`), and each label style variant's `leaderBase` writes its
flow's letters (`text`) 13 px from the aircraft towards the tag, in the tag's font and the track
colour (alerts included), with the leader starting 22 px out, beyond them (client with
`leaderBase`). The letters go round the disc with the tag: the CDG airborne `tagPositioning` puts
a new tag up and right (`initialBearing` 45, 85 px to its centre) and keeps it on the eight 45
degree positions while it is dragged (`snapWhileDragging`), 60 to 150 px out, so the letters take
one of eight places too. IRMA's airborne tags start and stay within the same distances, but drag freely. They were first 4 x 6 stroke glyphs under the disc (`font/A`…`font/Z`,
still in `shapes.json` with the old composites `cdg/arrsouth`…): too small, and scaled up they
blurred or outgrew the tag text. The CDG disc is three filled rectangles kept inside a 4.5 px radius (every client
fills rectangles) under a 1 px ring at 4.5 px, whose anti-aliased edge makes the disc round: the
client fills a circle (0.4.4) with hard pixel rows, no smoother than the rectangles, and an older
client would draw it hollow. Other polygons fill only when they are axis-aligned rectangles.

Every mapstyle carries the CoFrance route draw (thin `route_line` green, small crosses, fix labels
as 4-Flight's flight leg draws them: RobotoMono regular 12 px, a client font, on a dark slate box
with 4 px rounded corners, `cornerRadius`; the bold 10 px B612 on a square plate was hard to read) and the RDF circle (3 NM, off-white `225,225,215` at alpha 150: the radius is in NM and never clamped, so 10 NM
filled an approach display and 0.5 NM was too small to see; `circleThreshold` only hides one
smaller than that many pixels; the client has no RDF width or dash setting yet). `lowAltitude` is a
floor on pressure altitude below which no circle draws: at the schema default 3000 ft, finals, ground
and departures had none, so it is 0, the schema's minimum (a ground aircraft at a very high QNH,
whose pressure altitude dips below 0, still gets none).
Trails are vector shapes in the track colour, sized per mark by `historyTrailShape.scaleRamp`
(client 0.4.4): CDG's ring (`cdg/trail`, radius 4.5, stroke 1.3) at 3.5, 3.5, 2.5, 2.5, 1.5,
1.5 px radius, every mark inside the disc's size and on whole pixels (a ring of radius n + 0.5 on
the pixel grid is the crispest a small circle gets); IRMA's ring (`neoirma/trail`), three
at 5 px then three at 3 px, so the recent half of the trail stands out.
Profiles refresh like a radar (`map.sweepIntervalSeconds`, from `build.py`): approach every
`APPROACH_SWEEP_SECONDS` (2 s), AVISOs every `GROUND_SWEEP_SECONDS` (1 s). Aircraft and trails
move together once per sweep, never a mark on the aircraft. `historyTrailsSkipSteps` spaces the
marks in sweeps, counted back from the aircraft, and the trail still moves on every sweep: both
approach systems put a mark every other sweep (2, so 4 s apart); the AVISO ground looks one per sweep (1). A client before the fix
ignored it on a swept display (one mark per sweep), and without a sweep pinned the marks to
every n-th update, so the trail stalled and then jumped. The tag's vertical trend is text in the
tag font, as heavy as the rest of the tag: `↗` climbing, `↘` descending, a long dash `—` level
(the Lucide icons `:imove-up-right`… were too thin to read, and an arrow for level flight misled).

**Tags.** The airborne rows are the same in every system. The detailed tag (hover) shows
everything the compact one does, and more: never let a hover lose an item. While you hand a
flight to another controller (attention state 4), both show that controller's frequency after
the SID, in hand-off green (`nextControllerFrequency`), so you know what to tell the pilot. No runway item: at CDG
the runway is in the track colour and letter, and no other French airport lands on two runways
at once.

**Safety nets** (`policy.json`, the same in every system): STCA on the client's defaults (TopSky's
thresholds, 2.75 NM / 750 ft below 9500 ft, shown when one of the pair is yours), with the
final-approach corridor (2.5 NM in trail on final) and CDG's simultaneous runway pairs
(`stca.parallel`: arrivals 26L/27R and 08R/09L, departures 26R/27L and 08L/09R); the emergency
squawk (7500 HIJACK, 7600 RADIO FAILURE, 7700 EMERGENCY); RIMCAS on every runway, strips from the
navdata (`runwayMonitoring: {}`). The client draws an alert only where a tag, list or target asks
for it, so:

- every tag has an alert line on top (it collapses when empty): the alert's own words, white on
  red (CoFrance `alert_critical`) blinking until clicked (acknowledge) for an alert, dark on
  orange (CoFrance `alert`) for a warning (RIMCAS stage one); airborne tags add the manual alert
  (MISAP, INBEST, IRREG, WX) in CoFrance's warning yellow;
- the track symbol, and the forced one-minute alert vector, turn red / orange (`=alertTrack`,
  `=warningTrack` first in every `plotColor` and `speedVectorColor`).

No sounds are authored, so the nets are silent. Other nets (CLAM, BUST, MSAW, APW, TCT…) stay
off; MSAW and APW would need `msaw.geojson` / `areas.geojson` datasets.

The lists (`lists.yaml`) draw on CoFrance's list colours, nearly opaque, at 11 px: transparent,
their text could not be read over the map.

Rules and expressions shared by both live in `expressions.json`; `lists.yaml` is shared too.

Every system draws tags and route-draw labels in B612 Mono LFXX Bold (`fonts/B612MonoLFXX-Bold.ttf`): Airbus/ENAC's
cockpit-display font B612 Mono Bold, with a bar added in the zero so 0 and O differ (B612 draws
them alike). `scripts/font_zero.py` makes it from upstream's `B612Mono-Bold.ttf`. SIL OFL, no
reserved name: keep `B612-OFL.txt` beside it. 12 px takes the width and line height of 13 px
EuroScope, with taller capitals; the airborne tags are 13 px, since the pastel track colours on
the grey map read poorly at 12. A thinner stroke (`textWeight` -0.15) was tried and read worse.

**Squawks** are allocated by the NeoRadar server (provider `Server`); the vACC's allocator is set
in the hub, not in the package, so the manifest carries no `squawk` section. Each system's policy
can still rank or disable a provider by its name. The
schemas describe every field: <https://github.com/neoradar-project/schemas> (`systems/`).
`scripts/validate.js` also checks that every `=rule`, `$expression`, shape and `#system` named in
the systems exists, since the client silently ignores a broken one.

### Maps

- **CoFrance maps** are converted from the CoFrance config repo on every build
  (`scripts/cofrance.py`). Each CoFrance folder becomes one layer named "CoFrance …" and each map
  file one toggle. A CoFrance ASR's `EnabledMaps` line decides which ones its profile shows.
- **AVISO maps** are converted from the vSMR fork's AVISO files
  (`LFXX/Plugins/vSMR/vSMR_Data/AVISO/<ICAO>.geojson` in Sector-Files) on every build
  (`scripts/aviso.py`): one layer "AVISO <ICAO>" per airport, with items for the background, the
  ground layout (surfaces and guidance lines, in vSMR's paint order), each label kind (gates,
  taxiways, TORA…) and each vSMR group. A group named for a direction (LFPG's East / West Arrows)
  draws only while a runway end facing that way is active, for arrivals or departures. Colours
  are the palette the airport's ASR picks (`PLUGIN:vSMR:AvisoColorPalette`), else the file's
  default. Label zoom levels (and CoFrance maps' `zoomin` / `zoomout`) are on CoFrance's 0-10
  zoom scale, each level doubling the scale, 10 about an AVISO's opening view; they become
  `minPixelsPerNm` / `maxPixelsPerNm` through `zoom_px_per_nm` in `scripts/cofrance.py`
  (`ZOOM_10_PX_PER_NM` = 320: level 9 is 160 px/nm, 8 is 80). Gate labels (level 9) therefore show
  when an AVISO opens and hide only once it is zoomed well out. Raise or lower that one constant
  to move every threshold.
  Fix the content itself in Sector-Files: these files are what vSMR draws in EuroScope too.
- **Sector-file maps** come from the GNG `.sct` via neoradar-cli.

### Profiles

Profiles are converted from the ASRs on every build, then `finalize` adds:

- CoFrance displays: the system (`cdg`, `orly` or `neoirma`), transition altitude 5000, CoFrance's
  altitude filter and maps.
- AVISO displays: the `neoirma` system and exactly their airport's AVISO layer, nothing else.
  An airport with no vSMR AVISO file falls back to the sector file's `<ICAO> AVISO` region and
  `<ICAO> Groundlayout AVISO` geo, or its ground layout and runways.

To change a profile, change its ASR upstream.

### Patching upstream files

To change a source file before conversion without waiting for upstream, add a patch under
`diffs/<ID>/` (or `diffs/common/` for every package). See [diffs/README.md](../diffs/README.md).
For a simple text swap, use `transforms/replacements.json` (see
[transforms/README.md](../transforms/README.md)).

### Adding a package

Add an entry to `packages.json`: `id`, `name`, `namespace` (stable forever, it is the provider URL
and the server's vAcc id), `sectorFile` (basename in `LFXX/Sectors/`) and `firs` (source folders).

## Build warnings

The build prints warnings instead of failing for problems in the upstream data. Most need a fix
upstream.

| Warning | Meaning | What to do |
| --- | --- | --- |
| `ESE positions with no identifier, dropped` | GNG listed a position without its id; it would break the client | Report to the GNG/sector file maintainers |
| `… names N object(s) the sector file does not have, dropped` | An ASR names a runway, navaid or map that is gone (renumbered, withdrawn) | Fix the ASR in Sector-Files |
| `CoFrance maps named by ASRs but absent` | An ASR enables a CoFrance map that does not exist | Fix the ASR or add the map in CoFrance-config-files |
| `sets vSMR:Airport:X; using Y from its name` | An AVISO ASR points at the wrong airport | Fix the ASR in Sector-Files |
| `AVISO files not named by an ICAO code, not converted` | A variant such as `LFPO_Work.geojson`: vSMR loads `<ICAO>.geojson`, so no ASR selects it | Nothing; it would have overwritten the airport's own AVISO |
| `AVISO displays with no vSMR AVISO file` | No `vSMR_Data/AVISO/<ICAO>.geojson` for that airport; its AVISO comes from the sector file | Ask for the AVISO file in Sector-Files |
| `AVISO ASRs listing map items of their own` | An AVISO ASR names map content; the build replaces it with the airport's AVISO | Fix the ASR in Sector-Files |
| `AVISO … faces <direction> but no runway end does` | A vSMR group named for a direction matches no runway; it then draws whenever listed | Fix the group or the runways in the AVISO file |
| `AVISO displays drawing runways only` | The sector file has no ground layout for that airport | Nothing, or ask for a ground layout in GNG |
| `profiles use systems that shared/package/systems does not have` (fails the build) | `SYSTEM_FOR_TAG_FORMAT` names a system with no folder | Add the system or fix the mapping in `scripts/build.py` |
| `replacement … matched nothing` | Upstream changed text a transform expects | Update `transforms/replacements.json` |
| `ESE Parsing error` (neoradar-cli) | A malformed line in the GNG file, e.g. a SID with no route | Usually harmless; report to GNG if it matters |

## Known limits

- **One plugin.** The package ships `shared/package/plugins/vIFF-CDM-alpha.nrplugin`, the NeoRadar
  port of the CDM plugin ([vaccfr/vIFF-neoradar](https://github.com/vaccfr/vIFF-neoradar)); the
  build lists every `.nrplugin` there in the manifest, and the controller approves it in Plugin
  Settings. To update it, run that repo's
  `scripts/pack-nrplugin.sh --with-key <this repo>/shared/package/plugins` with the vIFF API key in its
  `.env`: it builds for Windows, macOS and Linux with the key built in and checks it is there. The key
  can be read back out of the archive, as from the EuroScope CDM plugin's DLL; the `.env` is never
  committed. Without `--with-key` the plugin only reads vIFF until a controller sets the key with
  `.cdm apikey`. The C# client loads only C#
  plugins, so the old C++ ones (vACDM, CCAMS, RPC, RampAgent, VATCAN) do not load. Tags and lists
  name no other plugin: the old `NeoVSID` tag item and `NeoVACDM` list are gone.
- **CDM configuration.** `shared/package/cdm/CDMconfig.xml` is the French vACC's CDM plugin config
  (from the Controller Pack, `LFXX/Plugins/CDM/`, with the FTP fields blanked: never commit an FTP
  password). The plugin reads it from the package's `cdm/` folder and downloads the `rate.txt`,
  `taxizones.txt`, `ctot.txt` and `sidInterval.txt` its URLs name (`vaccfr/vIFF-CDM`), so rates and
  taxi zones are maintained there, not here. Copy the file again when the Controller Pack's changes.
- **Server-dependent tags.** Arrival runway colours (CDG), SID/runway suggestions and route-based
  rules need the server link and the uploaded server dataset.
- **Not converted yet:** vSID procedure priorities and runway preferences.
- **CLI and schemas from `main`.** `NEORADAR_CLI_REF` / `NEORADAR_SCHEMAS_REF` in
  `.github/workflows/release.yml` (and `ref:` in `validate.yml`) pick the branches CI uses. Point
  them at `develop` only to try changes that have not reached `main` yet.

## Secrets used by the workflows

| Name | For |
| --- | --- |
| `LIVE_DATA_APP_ID` (variable), `LIVE_DATA_APP_PRIVATE_KEY` (secret) | Reading the private `data-sectorfiles` repo |
| `NEORADAR_R2_ACCESS_KEY_ID`, `NEORADAR_R2_SECRET_ACCESS_KEY` | An R2 API token with Object Read & Write on the `neoradar-packages` bucket, for uploading the package |
