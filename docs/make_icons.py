"""Draws the placeholder ribbon icons (16 and 32 px PNG, transparent) into addin/NoiseBoxAddin/Images and wires them into
Config.daml (smallImage / largeImage on every button and tool, image on the dock pane). Run: propy docs\\make_icons.py
Replace any PNG by your own artwork with the same file name; re-running this script overwrites the generated ones, so
copy your files in AFTER running it (the DAML only needs to be wired once and is not changed again).
"""
import os
import re

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, "addin", "NoiseBoxAddin", "Images")
DAML = os.path.join(ROOT, "addin", "NoiseBoxAddin", "Config.daml")
GROUP = {"scenario": "#1f3b5c", "source": "#d9822b", "terrain": "#3f7f4f", "struct": "#5b6b7f", "prop": "#1f8a8a", "analysis": "#2f6fa8"}

# id suffix (after NoiseBox_) -> (glyph, group)
MAP = {
    "Scenario_New": ("new", "scenario"), "Scenario_Open": ("folder", "scenario"), "Scenario_Save": ("save", "scenario"),
    "Scenario_Duplicate": ("copy", "scenario"),
    "SetLocation_FromLayer": ("layers", "source"), "SetLocation_Coordinates": ("cross", "source"),
    "SetLocation_PlaceOnMap": ("pin", "source"), "PlaceSourceTool": ("pin", "source"), "MoveSourceTool": ("move", "source"),
    "PickSourceTool": ("pick", "source"), "HeadingTool": ("heading", "source"), "Spectrum": ("bars", "source"),
    "Directivity": ("wedge", "source"),
    "Dtm_FromProject": ("mountain", "terrain"), "Dtm_Browse": ("folder", "terrain"), "Dtm_Coverage": ("coverage", "terrain"),
    "Dtm_None": ("flat", "terrain"), "Area_Polygons": ("polygon", "terrain"), "Area_DrawPolygon": ("polygon", "terrain"),
    "Area_DrawRectangle": ("rect", "terrain"), "Area_Radius": ("radius", "terrain"), "Area_MapExtent": ("extent", "terrain"),
    "AreaPolygonTool": ("polygon", "terrain"), "AreaRectangleTool": ("rect", "terrain"), "ReceiverGrid": ("grid", "terrain"),
    "Building_FromLayer": ("layers", "struct"), "Building_Draw": ("building", "struct"), "BuildingTool": ("building", "struct"),
    "Barrier_FromLayer": ("layers", "struct"), "Barrier_Sketch": ("wall", "struct"), "Barrier_Precise": ("wall", "struct"),
    "BarrierTool": ("wall", "struct"), "BarrierStartTool": ("pin", "struct"), "Enclosure_Rectangle": ("enclosure", "struct"),
    "Enclosure_Draw": ("enclosure", "struct"), "EnclosureTool": ("enclosure", "struct"), "PickStructureTool": ("pick", "struct"),
    "Ground": ("ground", "prop"), "Atmosphere": ("cloud", "prop"), "TerrainScreening": ("hill", "prop"), "Meteorology": ("wind", "prop"),
    "Preview": ("eye", "analysis"), "Run": ("play", "analysis"), "Results": ("chart", "analysis"), "Pane": ("bars", "analysis"),
}


def glyph(d, kind):
    """Draw on a 0..100 canvas (scaled by the caller). White shapes."""
    W = "white"
    L = lambda pts, w=7: d.line(pts, fill=W, width=w, joint="curve")
    if kind == "new":
        d.polygon([(26, 14), (60, 14), (76, 30), (76, 86), (26, 86)], outline=W, width=6); L([(60, 14), (60, 30), (76, 30)], 5); L([(51, 46), (51, 72)]); L([(38, 59), (64, 59)])
    elif kind == "folder":
        d.polygon([(14, 30), (40, 30), (48, 40), (86, 40), (86, 80), (14, 80)], outline=W, width=6)
    elif kind == "save":
        d.rectangle([20, 20, 80, 80], outline=W, width=6); d.rectangle([32, 20, 66, 40], fill=W); d.rectangle([34, 58, 66, 80], outline=W, width=5)
    elif kind == "copy":
        d.rectangle([18, 28, 58, 82], outline=W, width=6); d.rectangle([42, 14, 82, 68], outline=W, width=6)
    elif kind == "layers":
        for dy in (0, 16, 32):
            L([(50, 24 + dy), (82, 40 + dy), (50, 56 + dy), (18, 40 + dy), (50, 24 + dy)], 5)
    elif kind == "cross":
        d.ellipse([28, 28, 72, 72], outline=W, width=6); L([(50, 10), (50, 90)], 5); L([(10, 50), (90, 50)], 5)
    elif kind == "pin":
        d.ellipse([28, 12, 72, 56], fill=W); d.polygon([(32, 48), (68, 48), (50, 88)], fill=W); d.ellipse([42, 26, 58, 42], fill="#00000000")
    elif kind == "move":
        L([(50, 12), (50, 88)], 6); L([(12, 50), (88, 50)], 6)
        for p in ([(50, 8), (38, 24), (62, 24)], [(50, 92), (38, 76), (62, 76)], [(8, 50), (24, 38), (24, 62)], [(92, 50), (76, 38), (76, 62)]):
            d.polygon(p, fill=W)
    elif kind == "pick":
        d.polygon([(24, 12), (24, 78), (42, 62), (54, 88), (66, 82), (54, 58), (78, 58)], fill=W)
    elif kind == "heading":
        d.arc([18, 18, 82, 82], 200, 340, fill=W, width=6); d.polygon([(70, 14), (92, 36), (64, 38)], fill=W); L([(50, 80), (50, 50)], 6)
    elif kind == "bars":
        for i, h in enumerate((30, 50, 70, 55, 40)):
            x = 14 + i * 16; d.rectangle([x, 86 - h, x + 11, 86], fill=W)
    elif kind == "wedge":
        d.pieslice([6, 20, 94, 108], 230, 310, outline=W, width=6); L([(50, 64), (50, 64)], 6); d.ellipse([44, 58, 56, 70], fill=W)
    elif kind == "mountain":
        d.polygon([(8, 82), (36, 30), (52, 56), (66, 38), (92, 82)], fill=W)
    elif kind == "coverage":
        d.rectangle([16, 22, 84, 78], outline=W, width=6); L([(16, 50), (84, 50)], 4)
        d.rectangle([60, 22, 84, 78], fill=W)
    elif kind == "flat":
        L([(10, 60), (90, 60)], 8); L([(22, 74), (78, 74)], 4)
    elif kind == "polygon":
        d.polygon([(16, 66), (28, 22), (68, 14), (86, 54), (50, 84)], outline=W, width=6)
        for p in ((16, 66), (28, 22), (68, 14), (86, 54), (50, 84)):
            d.ellipse([p[0] - 7, p[1] - 7, p[0] + 7, p[1] + 7], fill=W)
    elif kind == "rect":
        d.rectangle([16, 24, 84, 76], outline=W, width=6)
        for p in ((16, 24), (84, 24), (16, 76), (84, 76)):
            d.rectangle([p[0] - 7, p[1] - 7, p[0] + 7, p[1] + 7], fill=W)
    elif kind == "radius":
        d.ellipse([12, 12, 88, 88], outline=W, width=6); L([(50, 50), (82, 28)], 6); d.ellipse([42, 42, 58, 58], fill=W)
    elif kind == "extent":
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            cx, cy = 50 + sx * 38, 50 + sy * 32
            L([(cx, cy - sy * 22), (cx, cy), (cx - sx * 22, cy)], 7)
    elif kind == "grid":
        for i in range(3):
            for j in range(3):
                x, y = 22 + i * 28, 22 + j * 28; d.ellipse([x - 8, y - 8, x + 8, y + 8], fill=W)
    elif kind == "building":
        d.rectangle([22, 14, 78, 88], outline=W, width=6)
        for i in range(2):
            for j in range(3):
                d.rectangle([34 + i * 20, 28 + j * 18, 42 + i * 20, 38 + j * 18], fill=W)
    elif kind == "wall":
        d.rectangle([12, 34, 88, 66], fill=W); L([(12, 78), (88, 78)], 4)
    elif kind == "enclosure":
        d.rectangle([14, 20, 86, 80], outline=W, width=7); d.ellipse([38, 38, 62, 62], fill=W)
    elif kind == "ground":
        L([(8, 50), (92, 50)], 7)
        for x in range(14, 90, 16):
            L([(x, 58), (x - 10, 84)], 5)
    elif kind == "cloud":
        d.ellipse([14, 44, 50, 80], fill=W); d.ellipse([34, 24, 74, 64], fill=W); d.ellipse([56, 42, 90, 78], fill=W); d.rectangle([32, 58, 74, 80], fill=W)
    elif kind == "hill":
        d.polygon([(6, 84), (36, 40), (64, 84)], fill=W); d.polygon([(40, 84), (66, 50), (94, 84)], outline=W, width=5); L([(36, 14), (36, 40)], 5)
    elif kind == "wind":
        for y, x2 in ((32, 76), (50, 88), (68, 64)):
            L([(10, y), (x2, y)], 6)
        d.arc([62, 18, 90, 46], 270, 90, fill=W, width=6)
    elif kind == "eye":
        d.ellipse([8, 28, 92, 72], outline=W, width=6); d.ellipse([36, 36, 64, 64], fill=W)
    elif kind == "play":
        d.polygon([(28, 14), (28, 86), (84, 50)], fill=W)
    elif kind == "chart":
        d.rectangle([14, 56, 30, 86], fill=W); d.rectangle([40, 36, 56, 86], fill=W); d.rectangle([66, 16, 82, 86], fill=W)
    else:
        raise KeyError(kind)


def make(name, kind, group):
    S = 512
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=S // 6, fill=GROUP[group])
    # draw the glyph on a 100 px canvas scaled 4x so line widths stay proportional
    big = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    gd = ImageDraw.Draw(big)
    S4 = 4

    class Scaled:
        """Proxy that multiplies every coordinate and width by S4."""
        def __getattr__(self, attr):
            fn = getattr(gd, attr)

            def call(*a, **k):
                def sc(v):
                    if isinstance(v, (list, tuple)) and v and isinstance(v[0], (list, tuple)):
                        return [tuple(y * S4 for y in x) for x in v]
                    return [x * S4 for x in v] if isinstance(v, (list, tuple)) else v
                a = list(a)
                a[0] = sc(a[0])
                if "width" in k:
                    k["width"] = k["width"] * S4
                return fn(*a, **k)
            return call
    glyph(Scaled(), kind)
    big = big.resize((int(S * 0.72), int(S * 0.72)), Image.LANCZOS)
    img.alpha_composite(big, (int(S * 0.14), int(S * 0.14)))
    for px in (16, 32):
        img.resize((px, px), Image.LANCZOS).save(os.path.join(IMG, "%s%d.png" % (name, px)))


def main():
    os.makedirs(IMG, exist_ok=True)
    txt = open(DAML, encoding="utf-8").read()
    ids = re.findall(r'<(?:button|tool) id="NoiseBox_([A-Za-z_]+)"', txt)
    missing = [i for i in ids if i not in MAP]
    if missing:
        raise SystemExit("no icon defined for: %s" % missing)
    for key, (kind, group) in MAP.items():
        make(key, kind, group)

    def wire(m):
        head = m.group(0)
        if "smallImage=" in head:
            return head
        key = m.group(2)
        return head.replace(' caption="', ' smallImage="Images/%s16.png" largeImage="Images/%s32.png" caption="' % (key, key), 1)
    txt = re.sub(r'<(button|tool) id="NoiseBox_([A-Za-z_]+)"[^>]*?>', wire, txt)
    if 'image="Images/Pane16.png"' not in txt:
        txt = txt.replace('<dockPane id="NoiseBox_Pane" caption="NoiseBox"', '<dockPane id="NoiseBox_Pane" caption="NoiseBox" image="Images/Pane16.png"')
    open(DAML, "w", encoding="utf-8").write(txt)
    print("wrote %d icon pairs to %s" % (len(MAP), IMG))


if __name__ == "__main__":
    main()
