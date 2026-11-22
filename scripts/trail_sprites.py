"""History-trail sprites from the old atlas, re-coloured into every trail colour.

    python scripts/trail_sprites.py

cdg: the old CDG trail, six rings shrinking from 10 to 4 px (plots/cdg/blanc/t1..t6).
neoirma: the old IRMA trail, three 4 px rings then three 3 px rings (plots/nce/F/t4, t5).
Writes shared/package/images/symbols.png + symbols.json (frames trails/<style>/<rrggbb>/<frame>)
and points every airborne variant's historyTrailImages at its colour's frames. Sprites, because
released clients cannot size a trail shape per mark (historyTrailShape.scaleRamp is not released).
"""
import json
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
SYSTEMS = REPO / "shared" / "package" / "systems"
IMAGES = REPO / "shared" / "package" / "images"
OLD = REPO / "backup" / "images"
STYLES = {
    "cdg": {"frames": {f"t{i}": f"plots/cdg/blanc/t{i}" for i in range(1, 7)},
            "trail": [f"t{i}" for i in range(1, 7)]},
    "neoirma": {"frames": {"big": "plots/nce/F/t4", "small": "plots/nce/F/t5"},
                "trail": ["big"] * 3 + ["small"] * 3},
}
SKIP_STEPS = 5  # the old CDG trail spacing


def trail_color(variant):
    c = (variant.get("historyTrailShape") or {}).get("color") or variant.get("plotColor")
    return tuple(c[:3]) if isinstance(c, list) else None


def main():
    old_atlas = Image.open(OLD / "symbols.png").convert("RGBA")
    old_frames = json.loads((OLD / "symbols.json").read_text(encoding="utf-8"))["frames"]

    def crop(name):
        f = old_frames[name]["frame"]
        return old_atlas.crop((f["x"], f["y"], f["x"] + f["w"], f["y"] + f["h"]))

    targets = {s: json.loads((SYSTEMS / s / "targets.json").read_text(encoding="utf-8")) for s in STYLES}
    rows = []  # (system, colour)
    for system, doc in targets.items():
        for v in doc["airborneSymbology"]:
            c = trail_color(v)
            if c and (system, c) not in rows:
                rows.append((system, c))

    size = 32
    width = max(len(s["frames"]) for s in STYLES.values())
    atlas = Image.new("RGBA", (size * width, size * len(rows)), (0, 0, 0, 0))
    frames = {}
    for row, (system, color) in enumerate(rows):
        key = "%02x%02x%02x" % color
        for i, (name, source) in enumerate(STYLES[system]["frames"].items()):
            src = crop(source)
            tinted = Image.new("RGBA", src.size, (*color, 0))
            tinted.putalpha(src.getchannel("A"))
            atlas.paste(tinted, (i * size, row * size))
            frames[f"trails/{system}/{key}/{name}"] = {
                "frame": {"x": i * size, "y": row * size, "w": size, "h": size}, "rotated": False, "trimmed": False,
                "spriteSourceSize": {"x": 0, "y": 0, "w": size, "h": size}, "sourceSize": {"w": size, "h": size},
                "pivot": {"x": 0.5, "y": 0.5},
            }
    atlas.save(IMAGES / "symbols.png")
    meta = {"app": "scripts/trail_sprites.py", "image": "symbols.png", "format": "RGBA8888", "size": {"w": atlas.width, "h": atlas.height}, "scale": 1}
    (IMAGES / "symbols.json").write_text(json.dumps({"frames": frames, "meta": meta}, indent=1) + "\n", encoding="utf-8", newline="\n")

    for system, doc in targets.items():
        for v in doc["airborneSymbology"]:
            c = trail_color(v)
            if not c:
                continue
            key = "%02x%02x%02x" % c
            v.pop("historyTrailShape", None)  # a trail shape would win over the images
            v["historyTrailImages"] = [f"trails/{system}/{key}/{name}" for name in STYLES[system]["trail"]]
            v["historyTrailsSkipSteps"] = SKIP_STEPS
        (SYSTEMS / system / "targets.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(rows)} trail colours, {len(frames)} frames")


if __name__ == "__main__":
    main()
