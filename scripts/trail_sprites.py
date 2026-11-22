"""History-trail sprites: the old CDG trail (6 rings shrinking from 10 to 4 px), in every trail colour.

    python scripts/trail_sprites.py

Re-colours plots/cdg/blanc/t1..t6 from backup/images/symbols.png into shared/package/images/
symbols.png + symbols.json (frames trails/<rrggbb>/t1..t6) and points every airborne variant's
historyTrailImages at its colour's frames. Sprites, because released clients cannot size a trail
shape per mark (historyTrailShape.scaleRamp is not released yet).
"""
import json
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
SYSTEMS = REPO / "shared" / "package" / "systems"
IMAGES = REPO / "shared" / "package" / "images"
OLD = REPO / "backup" / "images"
SOURCE = [f"plots/cdg/blanc/t{i}" for i in range(1, 7)]
SKIP_STEPS = 5  # the old CDG trail spacing


def trail_color(variant):
    c = (variant.get("historyTrailShape") or {}).get("color") or variant.get("plotColor")
    return tuple(c[:3]) if isinstance(c, list) else None


def main():
    old_atlas = Image.open(OLD / "symbols.png").convert("RGBA")
    old_frames = json.loads((OLD / "symbols.json").read_text(encoding="utf-8"))["frames"]
    sources = []
    for name in SOURCE:
        f = old_frames[name]["frame"]
        sources.append(old_atlas.crop((f["x"], f["y"], f["x"] + f["w"], f["y"] + f["h"])))
    size = sources[0].width

    targets = {s: json.loads((SYSTEMS / s / "targets.json").read_text(encoding="utf-8")) for s in ("cdg", "neoirma")}
    colors = []
    for doc in targets.values():
        for v in doc["airborneSymbology"]:
            c = trail_color(v)
            if c and c not in colors:
                colors.append(c)

    atlas = Image.new("RGBA", (size * len(sources), size * len(colors)), (0, 0, 0, 0))
    frames = {}
    for row, color in enumerate(colors):
        key = "%02x%02x%02x" % color
        for i, src in enumerate(sources):
            tinted = Image.new("RGBA", src.size, (*color, 0))
            tinted.putalpha(src.getchannel("A"))
            atlas.paste(tinted, (i * size, row * size))
            frames[f"trails/{key}/t{i + 1}"] = {
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
            v["historyTrailImages"] = [f"trails/{key}/t{i + 1}" for i in range(len(sources))]
            v["historyTrailsSkipSteps"] = SKIP_STEPS
        (SYSTEMS / system / "targets.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(colors)} trail colours, {len(frames)} frames")


if __name__ == "__main__":
    main()
