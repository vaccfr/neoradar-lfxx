"""Convert the CoFrance plugin's GeoJSON maps into NeoRadar map layers.

The CoFrance EuroScope plugin ships its own radar maps as GeoJSON under
LFXX/Plugins/CoFrance/maps/<FIR>/[<sector>/]<n>_<name>.geojson, in WGS84 with a
style vocabulary of its own. NeoRadar reads map layers as described by
@schemas/datasets/map-layer.schema.json: EPSG:3857 metres, an item table in the
header before the features, and a showWhen condition language over the
controller's session.

One CoFrance folder becomes one layer (datasets/maps/cofrance-<fir>[-<sector>].geojson)
and every CoFrance map file in it becomes one toggleable item of that layer, so a
CoFrance ASR's `PLUGIN:CoFrance:EnabledMaps:LFFF/LFPM/0_CCA_Seine,...` line maps
one to one onto profile map items (see `map_uuid`).

CoFrance `activation` rules become drawing-level showWhen conditions:
  activeRunways   {ICAO: {arr: [...], dep: [...]}}  -> has arrivalRunways / departureRunways
  unactiveRunway  (same shape)                       -> NOT of the above
  sectorOwnedByMe ["LFEE-HE", "LFFF-DG+LFFF-HP"]    -> has coveredPositions <ESE position id>
  sectorOwnedByOthers (same shape)                   -> NOT of the above
Within one airport and direction any listed runway satisfies the rule; airports
and directions combine with AND; '+' joins sectors that must all be covered.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

EARTH_RADIUS = 6378137.0
MAX_LAT = 85.05112878

# Symbols drawn for CoFrance pointStyle.type values, in the systems/shapes.json
# vocabulary (logical pixels, origin at the point, +y down). Drawn in the
# feature's lineStyle.color. Only filled axis-aligned rects are supported by the
# client, so "filled" glyphs nest a smaller outline instead.
_HEX = [[0, -4], [3.5, -2], [3.5, 2], [0, 4], [-3.5, 2], [-3.5, -2]]
SYMBOLS: dict[str, dict] = {
    "point": {"elements": [{"rect": {"size": [2, 2]}, "fill": True}]},
    "cross": {"elements": [{"line": [[-3, 0], [3, 0]]}, {"line": [[0, -3], [0, 3]]}]},
    "cross_large": {"elements": [{"line": [[-5, 0], [5, 0]]}, {"line": [[0, -5], [0, 5]]}]},
    "x": {"elements": [{"line": [[-3, -3], [3, 3]]}, {"line": [[3, -3], [-3, 3]]}]},
    "asterix": {"elements": [{"shapeRef": "cross"}, {"shapeRef": "x"}]},
    "circle": {"elements": [{"circle": {"radius": 3}}]},
    "circle_cross": {"elements": [{"circle": {"radius": 4}}, {"shapeRef": "cross", "scale": 1.34}]},
    "circle_with_outer_rings": {"elements": [{"circle": {"radius": 2}}, {"circle": {"radius": 4}}, {"circle": {"radius": 6}}]},
    "square": {"elements": [{"rect": {"size": [6, 6]}}]},
    "diamond": {"elements": [{"polygon": [[0, -4], [4, 0], [0, 4], [-4, 0]]}]},
    "diamond_cross": {"elements": [{"shapeRef": "diamond"}, {"shapeRef": "cross", "scale": 1.34}]},
    "triangle_hollow": {"elements": [{"polygon": [[0, -4], [4, 3], [-4, 3]]}]},
    "triangle_filled": {"elements": [{"polygon": [[0, -4], [4, 3], [-4, 3]]}, {"polygon": [[0, -2], [2, 2], [-2, 2]]}, {"line": [[0, -1], [0, 2]]}]},
    "triangle_hollow_thick_bottom_border": {"elements": [{"polygon": [[0, -4], [4, 3], [-4, 3]]}, {"line": [[-4, 4], [4, 4]]}]},
    "fix_filled": {"elements": [{"shapeRef": "triangle_filled"}]},
    "vor": {"elements": [{"polygon": _HEX}, {"rect": {"size": [1, 1]}, "fill": True}]},
    "vor_dme": {"elements": [{"shapeRef": "vor"}, {"rect": {"size": [10, 9]}}]},
    "dme": {"elements": [{"rect": {"size": [8, 8]}}, {"rect": {"size": [1, 1]}, "fill": True}]},
    "tacan": {"elements": [{"polygon": _HEX}, {"line": [[-3.5, -2], [-5.5, -5]]}, {"line": [[3.5, -2], [5.5, -5]]}, {"line": [[0, 4], [0, 7]]}]},
    "vortac": {"elements": [{"shapeRef": "tacan"}, {"rect": {"size": [1, 1]}, "fill": True}]},
    "ndb": {"elements": [{"circle": {"radius": 1.5}}, {"circle": {"radius": 3.5}}, {"circle": {"radius": 5.5}}]},
    "ndb_classic": {"elements": [{"shapeRef": "ndb"}]},
    "aerodrome": {"elements": [{"circle": {"radius": 4}}]},
    "aerodrome_ticks": {"elements": [{"circle": {"radius": 4}}, {"line": [[0, -4], [0, -6]]}, {"line": [[4, 0], [6, 0]]}, {"line": [[0, 4], [0, 6]]}, {"line": [[-4, 0], [-6, 0]]}]},
    "aerodrome_paved": {"elements": [{"circle": {"radius": 4}}, {"line": [[-2, 2], [2, -2]]}]},
    "aerodrome_paved_ticks": {"elements": [{"shapeRef": "aerodrome_ticks"}, {"line": [[-2, 2], [2, -2]]}]},
}
SMALL_SCALE = 0.7

# CoFrance's zoom scale (views.json, map zoomin/zoomout; vSMR's AVISO label zoomLevel uses the same
# 0-10 range): each level doubles the scale, 4 shows a whole FIR and 10 an airport, about an
# AVISO's opening view. NeoRadar draws by logical pixels per nautical mile, so level 10 is taken
# as ZOOM_10_PX_PER_NM (an AVISO window is about 5 nm across ~1700 px) and each level below halves it.
ZOOM_10_PX_PER_NM = 320


def zoom_px_per_nm(level) -> float | None:
    """Pixels per nautical mile at a CoFrance zoom level, or None for a level that limits nothing."""
    if not isinstance(level, (int, float)) or level <= 0:
        return None
    return round(ZOOM_10_PX_PER_NM * 2 ** (float(level) - 10), 2)


def slug(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def map_uuid(ref: str) -> str:
    """Item uuid of a CoFrance map, from its maps-relative path without extension
    ("LFFF/LFPM/0_CCA_Seine"), the form CoFrance ASRs list in EnabledMaps."""
    return "cofrance-" + slug(ref.replace("\\", "/").removesuffix(".geojson"))


def layer_source(group: str) -> str:
    return "maps/cofrance-" + slug(group)


def item_display_name(stem: str) -> str:
    return re.sub(r"^\d+(\.\d+)*_", "", stem).replace("_", " ").strip() or stem


def item_order(stem: str) -> int | None:
    m = re.match(r"^(\d+)", stem)
    return int(m.group(1)) if m else None


def to_mercator(lon: float, lat: float) -> list[float]:
    lat = max(min(lat, MAX_LAT), -MAX_LAT)
    x = EARTH_RADIUS * math.radians(lon)
    y = EARTH_RADIUS * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return [round(x, 3), round(y, 3)]


def project(coords):
    if coords and isinstance(coords[0], (int, float)):
        return to_mercator(coords[0], coords[1])
    return [project(c) for c in coords]


def color(value) -> list | None:
    if isinstance(value, list) and len(value) in (3, 4) and all(isinstance(v, (int, float)) for v in value):
        return [max(0, min(255, round(v))) for v in value]
    return None


@dataclass
class Report:
    warnings: list[str] = field(default_factory=list)
    unresolved_sectors: set[str] = field(default_factory=set)
    layers: int = 0
    items: int = 0
    drawings: int = 0

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


class ConditionBuilder:
    """Turns CoFrance activation objects into NeoRadar showWhen expressions."""

    def __init__(self, position_ids: dict[str, str], sector_ownership: dict, report: Report):
        self.position_ids = position_ids  # ESE callsign -> position id
        self.ownership = sector_ownership  # "LFEE-HE" -> [callsign, ...]
        self.report = report

    def _sector_position(self, sector: str) -> str | None:
        fir, _, code = sector.partition("-")
        candidates = [f"{fir}_{code}_CTR", f"{fir}__{code}_CTR"] + list(self.ownership.get(sector, []))
        for callsign in candidates:
            if callsign in self.position_ids:
                return self.position_ids[callsign]
        self.report.unresolved_sectors.add(sector)
        return None

    def _sectors(self, entries: list[str]):
        alternatives = []
        for entry in entries:
            parts = [self._sector_position(s.strip()) for s in entry.split("+")]
            if any(p is None for p in parts):
                continue
            terms = [["has", "coveredPositions", p] for p in parts]
            alternatives.append(terms[0] if len(terms) == 1 else ["AND", terms])
        if not alternatives:
            return None
        return alternatives[0] if len(alternatives) == 1 else ["OR", alternatives]

    @staticmethod
    def _runways(spec: dict):
        terms = []
        for icao, kinds in sorted(spec.items()):
            for kind, key in (("arr", "arrivalRunways"), ("dep", "departureRunways")):
                rwys = (kinds or {}).get(kind) or []
                alts = [["has", key, f"{icao}{r}"] for r in rwys]
                if alts:
                    terms.append(alts[0] if len(alts) == 1 else ["OR", alts])
        if not terms:
            return None
        return terms[0] if len(terms) == 1 else ["AND", terms]

    def build(self, activation: dict, where: str):
        terms = []
        for key, value in activation.items():
            if key == "activeRunways":
                cond = self._runways(value)
            elif key == "unactiveRunway":
                inner = self._runways(value)
                cond = ["NOT", [inner]] if inner else None
            elif key == "sectorOwnedByMe":
                cond = self._sectors(value)
                if cond is None:
                    # Every listed sector is unknown to this package's sector file: never true.
                    cond = ["has", "coveredPositions", "__unresolved__"]
            elif key == "sectorOwnedByOthers":
                inner = self._sectors(value)
                cond = ["NOT", [inner]] if inner else None
            else:
                self.report.warn(f"{where}: unknown activation key {key!r} ignored")
                cond = None
            if cond and cond[0] == "AND":
                terms.extend(cond[1])
            elif cond:
                terms.append(cond)
        if not terms:
            return None
        return terms[0] if len(terms) == 1 else ["AND", terms]


def _line_style(src: dict | None) -> dict | None:
    if not isinstance(src, dict):
        return None
    out = {}
    c = color(src.get("color"))
    if c is None:
        return None
    out["color"] = c
    if isinstance(src.get("width"), (int, float)) and src["width"] > 0:
        out["width"] = src["width"]
    if isinstance(src.get("opacity"), (int, float)):
        out["opacity"] = max(0.0, min(1.0, float(src["opacity"])))
    dash = src.get("dashArray")
    if isinstance(dash, list) and len(dash) >= 2 and all(isinstance(v, (int, float)) and v > 0 for v in dash):
        out["dashArray"] = dash if len(dash) % 2 == 0 else dash + dash
    return out


def _fill_style(src: dict | None) -> dict | None:
    if not isinstance(src, dict):
        return None
    c = color(src.get("color"))
    if c is None:
        return None
    out = {"color": c}
    if isinstance(src.get("opacity"), (int, float)):
        out["opacity"] = max(0.0, min(1.0, float(src["opacity"])))
    return out


def _text_style(src: dict) -> dict:
    out = {}
    c = color(src.get("color"))
    if c:
        out["color"] = c
    if isinstance(src.get("fontSize"), (int, float)) and src["fontSize"] > 0:
        out["fontSize"] = src["fontSize"]
    weight = src.get("fontWeight")
    if weight is not None:
        weight = str(weight)
        if weight in {"normal", "bold", "bolder", "lighter"} or weight in {str(n) for n in range(100, 1000, 100)}:
            out["fontWeight"] = weight
    return out


def _points(geometry: dict):
    if geometry["type"] == "Point":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPoint":
        return geometry["coordinates"]
    return []


def convert_file(path: Path, ref: str, group_label: str, conditions: ConditionBuilder, used_symbols: set, report: Report):
    """Returns (item, drawings) for one CoFrance map file."""
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    uuid = map_uuid(ref)
    stem = path.stem
    item = {"uuid": uuid, "name": item_display_name(stem)}
    order = item_order(stem)
    if order is not None:
        item["order"] = order

    features = [f for f in data.get("features", []) if f.get("geometry")]
    features.sort(key=lambda f: (f.get("properties") or {}).get("z-index", 0) or 0)
    drawings = []
    for feature in features:
        props = feature.get("properties") or {}
        geometry = feature["geometry"]
        base = {"uuid": uuid, "type": f"CoFrance {group_label}"}
        if isinstance(props.get("name"), str) and props["name"]:
            base["name"] = props["name"]
        # zoomin: drawn from that zoom level in; zoomout: drawn up to that level.
        if zoom_px_per_nm(props.get("zoomin")):
            base["minPixelsPerNm"] = zoom_px_per_nm(props["zoomin"])
        if zoom_px_per_nm(props.get("zoomout")):
            base["maxPixelsPerNm"] = zoom_px_per_nm(props["zoomout"])
        activation = props.get("activation")
        if isinstance(activation, dict) and activation:
            cond = conditions.build(activation, f"{ref}")
            if cond:
                base["showWhen"] = cond

        text_style = props.get("textStyle")
        point_style = props.get("pointStyle")
        if isinstance(text_style, dict) and _points(geometry):
            text = text_style.get("text") or props.get("name")
            if not text:
                continue
            for coords in _points(geometry):
                d = {**base, "text": str(text), "textStyle": _text_style(text_style)}
                drawings.append({"type": "Feature", "properties": d, "geometry": {"type": "Point", "coordinates": to_mercator(*coords[:2])}})
            continue
        if isinstance(point_style, dict) and _points(geometry):
            kind = point_style.get("type") or "point"
            if kind not in SYMBOLS:
                report.warn(f"{ref}: point type {kind!r} has no symbol, drawn as 'point'")
                kind = "point"
            if point_style.get("size") == "small":
                symbol = f"{kind}_small"
            else:
                symbol = kind
            if isinstance(point_style.get("opacity"), (int, float)) and point_style["opacity"] <= 0:
                continue
            c = color(point_style.get("color")) or [255, 255, 255]
            used_symbols.add(symbol)
            for coords in _points(geometry):
                d = {**base, "symbol": symbol, "lineStyle": {"color": c}}
                drawings.append({"type": "Feature", "properties": d, "geometry": {"type": "Point", "coordinates": to_mercator(*coords[:2])}})
            continue
        if geometry["type"] in ("Point", "MultiPoint"):
            # A bare point with neither text nor symbol draws nothing in CoFrance either.
            continue

        d = dict(base)
        ls = _line_style(props.get("lineStyle"))
        if ls:
            d["lineStyle"] = ls
        fs = _fill_style(props.get("fillStyle"))
        if fs and geometry["type"] in ("Polygon", "MultiPolygon"):
            d["fillStyle"] = fs
        if "lineStyle" not in d and "fillStyle" not in d:
            report.warn(f"{ref}: {geometry['type']} with no usable style skipped")
            continue
        drawings.append({"type": "Feature", "properties": d, "geometry": {"type": geometry["type"], "coordinates": project(geometry["coordinates"])}})
    return item, drawings


def _symbol_table(used: set[str]) -> dict:
    table = {}

    def add(name: str):
        if name in table:
            return
        base = name.removesuffix("_small")
        if name.endswith("_small"):
            add(base)
            table[name] = {"elements": [{"shapeRef": base, "scale": SMALL_SCALE}]}
            return
        shape = SYMBOLS[base]
        for el in shape["elements"]:
            if "shapeRef" in el:
                add(el["shapeRef"])
        table[name] = shape

    for name in sorted(used):
        add(name)
    return table


def _groups(maps_root: Path, folder: str):
    """Yields (group key, label, [(ref, path)]) for one CoFrance FIR folder:
    the FIR-level files, then each sector subfolder."""
    root = maps_root / folder
    if not root.is_dir():
        return
    top = sorted(p for p in root.glob("*.geojson"))
    if top:
        yield folder, folder, [(f"{folder}/{p.stem}", p) for p in top]
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        files = sorted(sub.glob("*.geojson"))
        if files:
            yield f"{folder}-{sub.name}", f"{folder} {sub.name}", [(f"{folder}/{sub.name}/{p.stem}", p) for p in files]


def convert(maps_root: Path, folders: list[str], out_dir: Path, position_ids: dict[str, str], plugin_version: str | None):
    """Writes datasets/maps/cofrance-*.geojson for the given CoFrance folders.
    Returns (manifest layer entries, set of item uuids, Report)."""
    report = Report()
    ownership_path = maps_root / "sector_ownership.json"
    ownership = json.loads(ownership_path.read_text(encoding="utf-8-sig")) if ownership_path.exists() else {}
    conditions = ConditionBuilder(position_ids, ownership, report)
    out_dir.mkdir(parents=True, exist_ok=True)
    layers, uuids = [], set()
    for folder in folders:
        for key, label, files in _groups(maps_root, folder):
            used_symbols: set[str] = set()
            items, drawings = [], []
            for ref, path in files:
                item, ds = convert_file(path, ref, label, conditions, used_symbols, report)
                if not ds:
                    report.warn(f"{ref}: no drawable features, item skipped")
                    continue
                items.append(item)
                drawings.extend(ds)
                uuids.add(item["uuid"])
            if not items:
                continue
            name = f"CoFrance {label}"
            origin = {"kind": "authored", "file": "CoFrance maps"}
            if plugin_version:
                origin["version"] = plugin_version
            doc = {"type": "FeatureCollection", "name": name, "origin": origin}
            if used_symbols:
                doc["symbols"] = _symbol_table(used_symbols)
            doc["items"] = items
            doc["features"] = drawings
            source = layer_source(key)
            target = out_dir / (source.removeprefix("maps/") + ".geojson")
            target.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
            layers.append({"name": name, "type": "geojson", "source": source, "hasLabels": False, "isLabelLayer": False})
            report.layers += 1
            report.items += len(items)
            report.drawings += len(drawings)
    return layers, uuids, report
