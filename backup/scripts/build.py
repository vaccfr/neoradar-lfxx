#!/usr/bin/env python3
"""Build the French vACC NeoRadar package environments.

    python scripts/build.py assemble --source <French vACC tree> [--only LFBB,LFMM]
    neoradar-cli convert build/<ID> <<< y            (per package)
    python scripts/build.py finalize [--only ...]
    neoradar-cli distribute build/<ID> --new-version <v> [--publish]

The source tree is a checkout of vaccfr/Sector-Files with the AIRAC data GNG
publishes laid over it, the layout the Controller Pack Installer produces:

    <FIR>/ASR/**.asr, <FIR>/Settings/LoginProfiles.txt, <FIR>/ICAO/*.txt, <FIR>/NavData/
    LFXX/Sectors/<FIR>.sct + .ese, LFXX/Sectors/current_airac.txt
    LFXX/Alias/alias.txt, LFXX/Plugins/CoFrance/maps/

`assemble` writes one neoradar-cli package environment per entry of packages.json
under build/<ID>/ (always from scratch), applies diffs/<ID>/*.patch and
diffs/common/*.patch, and converts the CoFrance maps. `finalize` runs after
neoradar-cli convert: it gives the converted profiles their ATM system, altitude
filter and CoFrance map items, and prunes manifest layers whose dataset is absent.

Standard library only.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cofrance  # noqa: E402
import tag_formats  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "shared"
SCHEMA_URL = "https://raw.githubusercontent.com/neoradar-project/schemas/refs/heads/main/package/manifest.schema.json"

# The sector-file layers neoradar-cli writes, in draw order, with the LFXX look.
SECTOR_LAYERS = [
    {"name": "region", "type": "geojson", "source": "region"},
    {"name": "artcc", "type": "geojson", "source": "artcc", "defaultStyle": {"lineStyle": {"color": [89, 89, 89], "width": 1, "opacity": 1, "dashArray": [2, 1]}}},
    {"name": "ARTCC High", "type": "geojson", "source": "artccHigh", "defaultStyle": {"lineStyle": {"color": [200, 200, 200], "width": 1, "opacity": 1, "dashArray": [2, 1]}}},
    {"name": "ARTCC Low", "type": "geojson", "source": "artccLow", "defaultStyle": {"lineStyle": {"color": [89, 89, 89], "width": 1, "opacity": 1, "dashArray": [2, 1]}}},
    {"name": "Low Airway", "type": "geojson", "source": "lowAirway", "defaultStyle": {"lineStyle": {"color": [83, 94, 78], "width": 1, "opacity": 1}}},
    {"name": "High Airway", "type": "geojson", "source": "highAirway", "defaultStyle": {"lineStyle": {"color": [83, 94, 78], "width": 1, "opacity": 1}}},
    {"name": "sid", "type": "geojson", "source": "sid", "defaultStyle": {"lineStyle": {"color": [83, 94, 78], "width": 1, "opacity": 1}}},
    {"name": "star", "type": "geojson", "source": "star", "defaultStyle": {"lineStyle": {"color": [83, 94, 78], "width": 1, "opacity": 1}}},
    {"name": "geo", "type": "geojson", "source": "geo"},
    {"name": "fix", "type": "geojson", "source": "fix", "hasLabels": True, "defaultStyle": {"pointStyle": {"type": "circle", "size": 3, "fillColor": [83, 94, 78], "fillOpacity": 1, "strokeOpacity": 1, "strokeWidth": 1}, "textStyle": {"color": [0, 255, 0], "fontSize": 12, "offset": [0, 0]}}},
    {"name": "vor", "type": "geojson", "source": "vor", "hasLabels": True, "defaultStyle": {"pointStyle": {"type": "square", "size": 3, "fillColor": [0, 0, 0], "fillOpacity": 1, "strokeOpacity": 1, "strokeWidth": 1}, "textStyle": {"color": [0, 255, 0], "fontSize": 12, "offset": [0, 0]}}},
    {"name": "ndb", "type": "geojson", "source": "ndb", "hasLabels": True, "defaultStyle": {"pointStyle": {"type": "square", "size": 3, "fillColor": [0, 0, 0], "fillOpacity": 1, "strokeOpacity": 1, "strokeWidth": 1}, "textStyle": {"color": [0, 255, 0], "fontSize": 12, "offset": [0, 0]}}},
    {"name": "airport", "type": "geojson", "source": "airport", "hasLabels": True},
    {"name": "runway", "type": "geojson", "source": "runway", "hasLabels": True, "defaultStyle": {"lineStyle": {"color": [0, 0, 0], "width": 2, "opacity": 1}}},
    {"name": "label", "type": "geojson", "source": "label", "isLabelLayer": True, "defaultStyle": {"textStyle": {"color": [255, 255, 255], "fontSize": 12, "offset": [0, 0]}}},
]

# CoFrance TagFormat -> NeoRadar ATM system (shared/package/systems/<name>).
# A CoFrance TagFormat with no system in build-info.json (no tag_formats.json entry) falls back here.
COFRANCE_DEFAULT_SYSTEM = "default"
SMR_SYSTEM = "default"
FRENCH_TRANSITION_ALTITUDE = 5000


def log(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    prefix = "::warning::" if _in_ci() else "WARNING: "
    print(prefix + msg, flush=True)


def _in_ci() -> bool:
    import os

    return os.environ.get("GITHUB_ACTIONS") == "true"


def load_config() -> dict:
    return json.loads((REPO / "packages.json").read_text(encoding="utf-8"))


def select(config: dict, only: str | None) -> list[dict]:
    pkgs = config["packages"]
    if not only:
        return pkgs
    wanted = {s.strip().upper() for s in only.split(",") if s.strip()}
    unknown = wanted - {p["id"] for p in pkgs}
    if unknown:
        sys.exit(f"Unknown package id(s): {', '.join(sorted(unknown))}")
    return [p for p in pkgs if p["id"] in wanted]


def read_text_any(path: Path) -> str:
    """Decodes UTF-8, falling back to Windows-1252, with line endings normalised to LF so a
    patch authored on Windows applies on the Linux runner."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    return text.replace("\r\n", "\n")


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def ese_positions(ese: Path) -> dict[str, str]:
    """Callsign -> position id from the ESE [POSITIONS] section."""
    out, section = {}, None
    for raw in read_text_any(ese).splitlines():
        line = raw.strip()
        if line.startswith("["):
            section = line.upper()
            continue
        if section == "[POSITIONS]" and line and not line.startswith(";"):
            parts = line.split(":")
            if len(parts) > 3 and parts[0] and parts[3]:
                out.setdefault(parts[0].strip(), parts[3].strip())
    return out


def apply_replacements(text: str, target_rel: str, rules: list[dict]) -> str:
    for rule in rules:
        if not fnmatch.fnmatch(target_rel, rule["appliesTo"]):
            continue
        count = text.count(rule["find"])
        if count == 0:
            warn(f"replacement {rule['find']!r} matched nothing in {target_rel}; upstream may have changed wording")
            continue
        text = text.replace(rule["find"], rule["replace"])
    return text


def copy_tree_text(src: Path, dst: Path, suffix: str) -> int:
    """Copies every *<suffix> file under src to dst, re-encoded as UTF-8 (the CLI reads UTF-8,
    the French files are partly Windows-1252)."""
    n = 0
    for f in sorted(src.rglob(f"*{suffix}")):
        target = dst / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(read_text_any(f), encoding="utf-8", newline="\n")
        n += 1
    return n


def drop_unidentified_positions(ese: Path) -> list[str]:
    """Removes [POSITIONS] lines whose identifier field (the 4th) is blank and returns their callsigns.

    Such a position cannot own airspace, and neoradar-cli turns the blank identifier into a sector
    with an empty id that the first such position "owns": the client reads a position's identifier
    as sectors[0] and throws on the empty one (EBOS_APP, LFBI_APP in GNG 2611). Works on bytes so
    the GNG file's encoding and line endings are kept as they are."""
    raw = ese.read_bytes()
    out, dropped, section = [], [], b""
    for line in raw.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith(b"["):
            section = stripped.upper()
        elif section == b"[POSITIONS]" and stripped and not stripped.startswith(b";"):
            fields = stripped.split(b":")
            if len(fields) > 3 and not fields[3].strip():
                dropped.append(fields[0].decode("latin-1"))
                continue
        out.append(line)
    if dropped:
        ese.write_bytes(b"".join(out))
    return dropped


def apply_diffs(env: Path, pkg_id: str) -> None:
    patches = sorted((REPO / "diffs" / "common").glob("*.patch")) + sorted((REPO / "diffs" / pkg_id).glob("*.patch"))
    for patch in patches:
        log(f"  applying {patch.relative_to(REPO)}")
        subprocess.run(
            ["git", "apply", "--whitespace=fix", f"--directory={env.relative_to(REPO).as_posix()}", str(patch)],
            cwd=REPO,
            check=True,
        )


def assemble(pkg: dict, config: dict, source: Path, build: Path) -> None:
    pid = pkg["id"]
    env = build / pid
    log(f"== assemble {pid} -> {env}")
    if env.exists():
        shutil.rmtree(env)
    env.mkdir(parents=True)
    rules = json.loads((REPO / "transforms" / "replacements.json").read_text(encoding="utf-8"))["rules"]
    sectors = source / "LFXX" / "Sectors"
    airac_file = sectors / "current_airac.txt"
    airac = airac_file.read_text(encoding="utf-8").strip() if airac_file.exists() else ""
    if not re.fullmatch(r"\d{4}", airac):
        sys.exit(f"{airac_file}: expected a 4-digit AIRAC cycle, got {airac!r}")

    # config.json
    pub = config["publish"]
    slug = pkg["namespace"]
    (env / "config.json").write_text(json.dumps({
        "sectorFileFromGNG": True,
        "publish": {
            "bucketName": pub["bucketName"],
            "region": pub["region"],
            "s3Path": pub["s3PathPrefix"] + slug,
            "makePublic": pub["makePublic"],
            "baseUrl": pub["baseUrlPrefix"] + slug,
        },
    }, indent=2) + "\n", encoding="utf-8")

    # sector_files/<ID>.sct + .ese
    (env / "sector_files").mkdir()
    for ext in ("sct", "ese"):
        src = sectors / f"{pkg['sectorFile']}.{ext}"
        if not src.is_file():
            sys.exit(f"Missing sector file {src}")
        for alias in pkg.get("sectorFileAliases", []):
            other = sectors / f"{alias}.{ext}"
            if other.is_file() and md5(other) != md5(src):
                warn(f"{other.name} differs from {src.name}; {pid} is built from {src.name} only")
        shutil.copyfile(src, env / "sector_files" / f"{pid}.{ext}")

    # ASRs: one FIR straight in, several FIRs one folder each
    asr_root = env / "ASRs"
    count = 0
    for fir in pkg["firs"]:
        target = asr_root if len(pkg["firs"]) == 1 else asr_root / fir
        count += copy_tree_text(source / fir / "ASR", target, ".asr")
    log(f"  {count} ASR files")

    # euroscope_data: alias + one LoginProfiles.txt, the FIRs' files concatenated so the CLI
    # groups every profile by callsign prefix (the first FIR wins a duplicated callsign)
    ed = env / "euroscope_data"
    ed.mkdir()
    alias = source / "LFXX" / "Alias" / "alias.txt"
    (ed / "Alias.txt").write_text(read_text_any(alias), encoding="utf-8", newline="\n")
    rel = "euroscope_data/LoginProfiles.txt"
    chunks = []
    for fir in pkg["firs"]:
        lp = source / fir / "Settings" / "LoginProfiles.txt"
        if not lp.is_file():
            warn(f"{lp} missing")
            continue
        chunks.append(apply_replacements(read_text_any(lp), f"{rel} ({fir})", rules).rstrip("\n"))
    (env / rel).write_text("\n".join(chunks) + "\n", encoding="utf-8", newline="\n")

    # icao_data
    data_folder = pkg.get("dataFolder", pkg["firs"][0])
    icao = env / "icao_data"
    icao.mkdir()
    for name in ("ICAO_Aircraft.txt", "ICAO_Airlines.txt", "ICAO_Airports.txt"):
        src = source / data_folder / "ICAO" / name
        if not src.is_file():
            src = source / "LFXX" / "ICAO" / name
        shutil.copyfile(src, icao / name)
    shutil.copyfile(SHARED / "icao_data" / "recat.json", icao / "recat.json")

    # NavData for build-airways: server-only, kept outside package/
    navdata = source / data_folder / "NavData"
    if navdata.is_dir():
        shutil.copytree(navdata, env / "navdata")

    # package/: shared content + manifest
    package = env / "package"
    shutil.copytree(SHARED / "package", package, ignore=shutil.ignore_patterns(".gitkeep", ".DS_Store"))
    (package / "datasets").mkdir(exist_ok=True)

    plugin_version = None
    version_file = source / "LFXX" / "Plugins" / "CoFrance" / "version.json"
    if version_file.exists():
        plugin_version = json.loads(version_file.read_text(encoding="utf-8-sig")).get("plugin_version")
    maps_root = source / "LFXX" / "Plugins" / "CoFrance" / "maps"
    positions = ese_positions(env / "sector_files" / f"{pid}.ese")
    layers, uuids, report = cofrance.convert(
        maps_root, config.get("sharedCoFranceMaps", []) + pkg["firs"], package / "datasets" / "maps", positions, plugin_version
    )
    log(f"  CoFrance: {report.layers} layers, {report.items} items, {report.drawings} drawings")
    for w in report.warnings:
        warn(f"CoFrance {pid}: {w}")
    if report.unresolved_sectors:
        warn(f"CoFrance {pid}: sectors with no position in {pid}.ese (their sector-ownership rules never show): "
             + ", ".join(sorted(report.unresolved_sectors)))

    # One ATM system per CoFrance tag format the package's ASRs use (scripts/tag_formats.py).
    used_formats = {
        parse_asr(a)["plugin"].get(("CoFrance", "TagFormat"), "")
        for a in (env / "ASRs").rglob("*.asr")
    } - {""}
    formats_file = source / "LFXX" / "Plugins" / "CoFrance" / "config" / "tag_formats.json"
    if formats_file.is_file():
        format_systems, format_warnings = tag_formats.generate(formats_file, package / "systems", used_formats)
        for w in format_warnings:
            warn(f"{pid}: {w}")
        generated = sorted({s for f, s in format_systems.items() if f in used_formats and s.startswith("cf-")})
        log(f"  {len(generated)} systems generated from CoFrance tag formats: {', '.join(generated)}")
    else:
        warn(f"{formats_file} missing: every CoFrance profile falls back to {COFRANCE_DEFAULT_SYSTEM}")
        format_systems = {}
    unmapped = sorted(used_formats - set(format_systems))
    if unmapped:
        warn(f"{pid}: tag formats used by ASRs but absent from tag_formats.json, shown as {COFRANCE_DEFAULT_SYSTEM}: {', '.join(unmapped)}")

    fonts = sorted(p.name for p in (package / "fonts").glob("*.ttf"))
    manifest = {
        "$schema": SCHEMA_URL,
        "id": pid,
        "name": pkg["name"],
        "version": airac,
        "description": f"{pkg['description']}, AIRAC {airac}",
        "namespace": pkg["namespace"],
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "mapLayers": SECTOR_LAYERS + layers,
        "fonts": [{"alias": Path(f).stem, "src": f} for f in fonts],
        "plugins": [],
    }
    (package / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (env / "build-info.json").write_text(json.dumps({
        "id": pid,
        "airac": airac,
        "sectorFile": f"{pkg['sectorFile']}.sct",
        "sectorFileMd5": md5(env / "sector_files" / f"{pid}.sct"),
        "cofrancePluginVersion": plugin_version,
        "cofranceItems": sorted(uuids),
        "tagFormatSystems": format_systems,
    }, indent=2) + "\n", encoding="utf-8")

    apply_diffs(env, pid)
    dropped = drop_unidentified_positions(env / "sector_files" / f"{pid}.ese")
    if dropped:
        warn(f"{pid}: ESE positions with no identifier, dropped (they cannot own airspace and break the client): {', '.join(dropped)}")


def parse_asr(path: Path) -> dict:
    out = {"plugin": {}}
    for line in read_text_any(path).splitlines():
        if line.startswith("PLUGIN:"):
            parts = line.split(":", 3)
            if len(parts) == 4:
                out["plugin"][(parts[1], parts[2])] = parts[3].strip()
        elif ":" in line:
            key, _, value = line.partition(":")
            out.setdefault(key.strip(), value.strip())
    return out


def layer_items(datasets: Path, source: str) -> list[dict]:
    path = datasets / f"{source}.geojson"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("items", [])


def aviso_items(sector_items: dict[str, list[dict]], icao: str) -> list[str]:
    """The sector-file items an AVISO of `icao` draws. The major airports have dedicated ones:
    the '<ICAO> AVISO' region(s) and the '<ICAO> Groundlayout AVISO' geo (and variants such as
    '... Gates'). The others only have their '<ICAO> Groundlayout <name>' geo, drawn with the
    airport's runways. An airport with no ground layout at all gets its runways alone.
    Returns (uuids, kind) where kind is 'aviso', 'layout' or 'runways'."""
    if not re.fullmatch(r"[A-Z]{4}", icao):
        return [], ""

    def named(source: str, prefix: str) -> list[str]:
        return [i["uuid"] for i in sector_items.get(source, []) if i["name"].upper().startswith(prefix)]

    dedicated = named("region", f"{icao} AVISO") + named("geo", f"{icao} GROUNDLAYOUT AVISO")
    if dedicated:
        return dedicated, "aviso"
    runways = named("runway", f"{icao}-")
    layout = named("geo", f"{icao} GROUNDLAYOUT")
    if layout:
        return layout + runways, "layout"
    return runways, "runways"


def finalize(pkg: dict, build: Path) -> None:
    pid = pkg["id"]
    env = build / pid
    log(f"== finalize {pid}")
    info = json.loads((env / "build-info.json").read_text(encoding="utf-8"))
    known = set(info["cofranceItems"])
    format_systems = info.get("tagFormatSystems", {})
    package = env / "package"
    profiles = package / "profiles"

    sector_items = {s: layer_items(package / "datasets", s) for s in ("region", "geo", "runway")}
    missing_maps: set[str] = set()
    no_aviso: set[str] = set()
    runways_only: set[str] = set()
    dangling: dict[str, list[str]] = {}
    all_items = {
        item["uuid"]
        for layer in (package / "datasets").rglob("*.geojson")
        for item in json.loads(layer.read_text(encoding="utf-8")).get("items", [])
    }
    touched = 0
    for asr in sorted((env / "ASRs").rglob("*.asr")):
        rel = asr.relative_to(env / "ASRs").with_suffix(".stp")
        stp = profiles / rel
        if not stp.is_file():
            warn(f"{pid}: no converted profile for {asr.relative_to(env)}")
            continue
        meta = parse_asr(asr)
        profile = json.loads(stp.read_text(encoding="utf-8"))
        if meta.get("DisplayTypeName", "").lower().startswith("cofrance"):
            fmt = meta["plugin"].get(("CoFrance", "TagFormat"), "")
            profile["atmSystem"] = format_systems.get(fmt, COFRANCE_DEFAULT_SYSTEM)
            radar = profile.setdefault("radarData", {})
            radar["transitionAltitude"] = FRENCH_TRANSITION_ALTITUDE
            for key, field in (("UpperAlt", "upperFilterValue"), ("LowerAlt", "lowerFilterValue")):
                enabled = meta["plugin"].get(("CoFrance", f"{key}Enabled"), "0") == "1"
                value = meta["plugin"].get(("CoFrance", key))
                if enabled and value and value.lstrip("-").isdigit():
                    radar[field] = int(value)
            items = profile["map"].setdefault("items", [])
            present = {i["uuid"] for i in items}
            for ref in filter(None, (r.strip() for r in meta["plugin"].get(("CoFrance", "EnabledMaps"), "").split(","))):
                uuid = cofrance.map_uuid(ref)
                if uuid not in known:
                    missing_maps.add(ref)
                    continue
                if uuid not in present:
                    items.append({"showLabel": False, "uuid": uuid})
                    present.add(uuid)
        elif meta.get("DisplayTypeName", "").lower().startswith("smr"):
            # vSMR displays (the AVISOs) use the ground look of shared/package/systems/default. Named
            # explicitly: with no atmSystem the client falls back to the first system, cdg (approach).
            profile["atmSystem"] = SMR_SYSTEM
        if meta.get("DisplayTypeName", "").lower().startswith("smr") and not profile["map"].get("items"):
            # The French AVISO ASRs carry no map content (Sector-Files' maintenance script strips it):
            # the vSMR fork draws the AVISO of PLUGIN:vSMR:Airport itself. An empty item list would
            # draw every layer, so list that airport's AVISO items the way vSMR picks them.
            icao = meta["plugin"].get(("vSMR", "Airport"), "").strip().upper()
            named_icao = re.match(r"^([A-Z]{4}) .*AVISO$", asr.stem.upper())
            if named_icao and named_icao.group(1) != icao:
                # The file is named for one airport and points vSMR at another: a copy-paste slip
                # upstream. The name is what the controller picks the display by.
                warn(f"{pid}: {asr.name} sets vSMR:Airport:{icao or '(none)'}; using {named_icao.group(1)} from its name")
                icao = named_icao.group(1)
            uuids, kind = aviso_items(sector_items, icao)
            if uuids:
                profile["map"]["items"] = [{"showLabel": False, "uuid": u} for u in uuids]
                if kind == "runways":
                    runways_only.add(icao)
            else:
                no_aviso.add(f"{asr.relative_to(env / 'ASRs').as_posix()} ({icao or 'no vSMR airport'})")
        # An ASR entry naming an object the sector file no longer has (a renumbered runway, a
        # withdrawn navaid) converts to an item no layer holds: EuroScope ignores such a line, so
        # drop the row and report it, upstream's ASR is what needs the fix.
        kept_items = []
        for item in profile["map"].get("items", []):
            if item["uuid"] in all_items:
                kept_items.append(item)
            else:
                dangling.setdefault(asr.relative_to(env / "ASRs").as_posix(), []).append(item["uuid"])
        profile["map"]["items"] = kept_items
        stp.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
        touched += 1
    log(f"  {touched} profiles finalized")
    if runways_only:
        warn(f"{pid}: AVISO displays drawing runways only, the sector file has no ground layout for: {', '.join(sorted(runways_only))}")
    if no_aviso:
        warn(f"{pid}: AVISO displays whose airport has no AVISO or ground layout items in the sector file, left showing every layer: {', '.join(sorted(no_aviso))}")
    for name, uuids in sorted(dangling.items()):
        warn(f"{pid}: {name} names {len(uuids)} object(s) the sector file does not have, dropped: {', '.join(sorted(set(uuids)))}")
    if missing_maps:
        warn(f"{pid}: CoFrance maps named by ASRs but absent from the CoFrance maps folder: {', '.join(sorted(missing_maps))}")

    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    kept = []
    for layer in manifest["mapLayers"]:
        if (package / "datasets" / f"{layer['source']}.geojson").is_file():
            kept.append(layer)
        else:
            log(f"  manifest: dropping layer {layer['source']!r}, no dataset")
    manifest["mapLayers"] = kept
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    for stray in package.rglob("neoradar-cli.log"):
        stray.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("assemble", help="write build/<ID> package environments from the source tree")
    a.add_argument("--source", required=True, type=Path)
    f = sub.add_parser("finalize", help="post-process build/<ID> after neoradar-cli convert")
    for p in (a, f):
        p.add_argument("--only", help="comma-separated package ids (default: all)")
        p.add_argument("--build", type=Path, default=REPO / "build")
    sub.add_parser("ids", help="print the package ids as a JSON array (for CI matrices)")
    args = parser.parse_args()

    config = load_config()
    if args.command == "ids":
        print(json.dumps([p["id"] for p in config["packages"]]))
        return 0
    build = args.build.resolve()
    for pkg in select(config, args.only):
        if args.command == "assemble":
            assemble(pkg, config, args.source.resolve(), build)
        else:
            finalize(pkg, build)
    return 0


if __name__ == "__main__":
    sys.exit(main())
