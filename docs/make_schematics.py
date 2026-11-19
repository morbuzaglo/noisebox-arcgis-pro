"""Draws the ribbon and pane SCHEMATICS used in the manual (propy or any Python with matplotlib).

These are drawings made from the add-in's design (Config.daml and the pane layout). They are NOT screenshots: the add-in
has not been compiled or loaded into ArcGIS Pro yet.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
NAVY, BLUE, GREY, LIGHT, ORANGE, RED = "#1f3b5c", "#2f6fa8", "#6b7280", "#eef2f7", "#d9822b", "#b42318"


def box(ax, x, y, w, h, fc="white", ec=GREY, lw=0.8, r=0.01):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=%g" % r, fc=fc, ec=ec, lw=lw))


def ribbon():
    groups = [("Scenario", ["New", "Open", "Save", "Duplicate"]),
              ("Source", ["Set Location ▾", "Source\nSpectrum", "Directivity"]),
              ("Terrain and Area", ["Select DTM ▾", "Set Analysis\nArea ▾", "Receiver\nGrid"]),
              ("Structures", ["Add\nBuilding ▾", "Add Noise\nBarrier ▾", "Add\nEnclosure ▾"]),
              ("Propagation", ["Ground", "Atmosphere", "Terrain\nScreening", "Meteorology"]),
              ("Analysis", ["Preview", "Run", "Results"])]
    fig, ax = plt.subplots(figsize=(15, 2.6))
    ax.set_xlim(0, 100); ax.set_ylim(0, 22); ax.axis("off")
    box(ax, 0, 0, 100, 22, fc=LIGHT)
    ax.text(1.2, 19.0, "NoiseBox", fontsize=10, color="white", fontweight="bold", bbox=dict(boxstyle="round,pad=0.35", fc=BLUE, ec=BLUE))
    n = sum(len(b) for _, b in groups)
    gap = 1.0
    unit = (98.0 - gap * len(groups)) / n
    x = 1.0
    for title, btns in groups:
        w = len(btns) * unit
        box(ax, x, 1.0, w, 15.5, fc="white", ec="#c7cdd6", r=0.3)
        ax.text(x + w / 2, 2.4, title, ha="center", fontsize=8, color=GREY)
        for i, b in enumerate(btns):
            bx = x + i * unit + unit * 0.06
            box(ax, bx, 5.0, unit * 0.88, 10.0, fc="#dbe7f5", ec=BLUE, r=0.4)
            ax.text(bx + unit * 0.44, 10.0, b, ha="center", va="center", fontsize=5.8, color=NAVY)
        x += w + gap
    fig.savefig(os.path.join(OUT, "ribbon.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


def pane(name, sections, open_section, body, status, notes=None, figsize=(3.9, 8.4)):
    H = 215
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(0, 100); ax.set_ylim(0, H); ax.axis("off")
    box(ax, 0, 0, 100, H, fc="white", ec=GREY, lw=1.2, r=0.8)
    ax.add_patch(Rectangle((0, H - 10), 100, 10, fc=NAVY, ec=NAVY))
    ax.text(4, H - 5, "NoiseBox", color="white", fontsize=9, fontweight="bold", va="center")
    y = H - 13
    for title, summary in sections:
        if title == open_section:
            ax.add_patch(Rectangle((2, y - 7), 96, 7, fc=LIGHT, ec="#c7cdd6"))
            ax.text(5, y - 3.5, "▾ " + title, fontsize=8, fontweight="bold", va="center", color=NAVY)
            y -= 8
            for kind, text in body:
                if kind == "label":
                    ax.text(6, y - 2.5, text, fontsize=6.6, color=GREY, va="center"); y -= 5
                elif kind == "field":
                    box(ax, 6, y - 6, 88, 5.2, fc="white", ec="#9aa3af", r=0.3)
                    ax.text(8, y - 3.4, text, fontsize=7, va="center"); y -= 7.2
                elif kind == "bad":
                    box(ax, 6, y - 6, 88, 5.2, fc="#fdecea", ec=RED, r=0.3)
                    ax.text(8, y - 3.4, text, fontsize=7, va="center", color=RED); y -= 7.2
                elif kind == "button":
                    box(ax, 6, y - 6, 42, 5.4, fc="#dbe7f5", ec=BLUE, r=0.3)
                    ax.text(27, y - 3.2, text, fontsize=7, ha="center", va="center", color=NAVY); y -= 7.4
                elif kind == "row":
                    ax.text(8, y - 2.6, text[0], fontsize=6.8, va="center", family="monospace")
                    box(ax, 34, y - 5, 40, 4.4, fc="white", ec="#9aa3af", r=0.2)
                    ax.text(36, y - 2.8, text[1], fontsize=6.8, va="center", family="monospace", color=(RED if text[1] == "" else "black"))
                    y -= 5.4
                elif kind == "note":
                    ax.text(6, y - 2.5, text, fontsize=6.4, color=GREY, va="center", style="italic"); y -= 5
                elif kind == "item":
                    ax.text(8, y - 2.6, text, fontsize=6.8, va="center"); y -= 5.2
                elif kind == "gap":
                    y -= text
            y -= 2
        else:
            ax.add_patch(Rectangle((2, y - 7), 96, 7, fc="white", ec="#c7cdd6"))
            ax.text(5, y - 3.5, "▸ " + title, fontsize=8, fontweight="bold", va="center", color=NAVY)
            ax.text(52, y - 3.5, summary, fontsize=6.0, va="center", color=GREY)
            y -= 8
    box(ax, 0, 0, 100, 14, fc=LIGHT, ec="#c7cdd6", r=0.2)
    box(ax, 4, 7.5, 20, 5, fc="#dbe7f5", ec=BLUE, r=0.3); ax.text(14, 10, "Preview", ha="center", va="center", fontsize=7.5)
    box(ax, 27, 7.5, 20, 5, fc=BLUE, ec=BLUE, r=0.3); ax.text(37, 10, "Run", ha="center", va="center", fontsize=7.5, color="white", fontweight="bold")
    ax.text(52, 10, status[0], fontsize=7, va="center", color=(RED if "error" in status[0] else GREY))
    ax.text(4, 3.8, status[1], fontsize=6.4, va="center", color=GREY)
    fig.savefig(os.path.join(OUT, name), dpi=170, bbox_inches="tight")
    plt.close(fig)


def main():
    os.makedirs(OUT, exist_ok=True)
    ribbon()
    secs = [("Scenario", "Drill rig, baseline"), ("Source", "Drill-01, 1.2 m above ground"),
            ("Terrain and Area", "dem_sample, 5 m output cells"), ("Structures", "1 barrier, 1 enclosure"),
            ("Propagation", "iso2024, G = 0.5"), ("Outputs", "A_baseline"), ("Issues", "0 errors")]
    secs[2] = ("Terrain and Area", "dem, 5 m cells")
    secs[1] = ("Source", "Drill-01, 1.2 m")
    secs[3] = ("Structures", "1 barrier, 1 encl.")
    pane("pane_source.png", secs, "Source", [
        ("label", "Location: from layer"), ("field", "Sources  ▾"), ("button", "Use this layer point"),
        ("label", "Location: coordinates (EPSG 2039)"), ("label", "Easting"), ("field", "180000"), ("label", "Northing"), ("field", "665000"),
        ("label", "Source height above ground (m)"), ("field", "1.2"),
        ("note", "Ground 21.0 m + height 1.2 m = 22.2 m absolute"),
        ("label", "Spectrum  Lw, dB re 1 pW"), ("row", ("  63 Hz", "92")), ("row", (" 125 Hz", "96")), ("row", (" 250 Hz", "98")), ("row", (" 500 Hz", "97")),
        ("row", ("1000 Hz", "94")), ("row", ("2000 Hz", "90")), ("row", ("4000 Hz", "85")), ("row", ("8000 Hz", "78")),
        ("button", "Paste"), ], ("Ready", "Source set from coordinates."))
    pane("pane_issues.png", secs[:6] + [("Issues", "")], "Issues", [
        ("item", "✖ Source height above ground is missing."),
        ("note", "   → Enter the physical height ... in metres"),
        ("item", "✖ Lw is missing in 1 band(s): 125 Hz. A missing"),
        ("note", "   value is not the same as 0 dB."),
        ("item", "⚠ DTM cell (30 m) is coarser than the output"),
        ("note", "   cell (5 m); the output is finer than the terrain."),
        ("note", "Click an issue to go straight to the input."),
    ], ("2 errors, 0 warnings", "2 error(s) stop the run. Click one ..."))
    pane("pane_structures.png", secs, "Structures", [
        ("item", "☑ Screen          Noise barrier"), ("note", "     ☑ Drawn on map   in the run, drawn"),
        ("item", "☑ Enclosure       Enclosure"), ("note", "     ☐ Drawn on map   in the run, hidden on the map"),
        ("button", "Edit"), ("label", "Vertical definition"), ("item", "● Constant height above local terrain"),
        ("item", "○ Fixed absolute top elevation"), ("label", "Height above local terrain (m)"), ("field", "4"),
        ("item", "☐ Also calculate transmission"), ("note", "Unchecked: diffraction only (ISO 9613-2)."),
        ("button", "Profile preview"),
    ], ("Ready", "Selecting a row highlights it on the map."))
    print("schematics written to", OUT)


if __name__ == "__main__":
    main()
