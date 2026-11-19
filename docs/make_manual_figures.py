"""Runs the manual's worked example through the real engine and draws the figures (propy).

    propy docs\\make_manual_figures.py <workdir>

Writes PNGs + figures.json into docs/figures/. Everything drawn from results is real output of the NoiseBox run (3 MATLAB
runs); the pane and ribbon drawings are schematics and are labelled as such in the manual.
"""
import copy
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle, FancyBboxPatch

from common import *  # noqa: F401,F403
from scn_common import *  # noqa: F401,F403
from noisebox import pipeline, scenario as SC, scenario_run as R

OUT = os.path.join(ROOT, "docs", "figures")
LOG = pipeline.PrintLog()
LW_DRILL = [92.0, 96.0, 98.0, 97.0, 94.0, 90.0, 85.0, 78.0]
NAVY, ORANGE, GREY = "#1f3b5c", "#d9822b", "#6b7280"


def example(gdb, tag, structures):
    sc = base_scenario(gdb, run=tag, dtm=DEM_SAMPLE)
    sc["name"] = "Drill rig, baseline" if not structures else "Drill rig, " + tag
    sc["source"]["name"] = "Drill-01"
    sc["source"]["height_m"] = 1.2
    sc["source"]["spectrum"]["lw"] = list(LW_DRILL)
    sc["source"]["spectrum"]["profile"] = "Drill rig (example)"
    sc["area"].update({"mode": "extent", "extent": [X0 - 60, Y0 - 100, X0 + 240, Y0 + 100], "input_wkid": 2039})
    sc["area"]["cell"] = {"mode": "custom", "size_m": 5.0}
    sc["area"]["receiver_height_m"] = 1.5
    sc["outputs"].update({"overall_z": True, "bands": [500, 1000], "limit_dba": 55.0, "detail": "Levels only",
                          "shared_scale": {"min": 35.0, "max": 75.0}})
    sc["structures"] = structures
    return sc


def arr_and_extent(path):
    import arcpy
    r = arcpy.Raster(path)
    e = r.extent
    return raster(path), (e.XMin, e.XMax, e.YMin, e.YMax)


def draw_scene(ax, with_barrier, with_enclosure):
    ax.plot([X0], [Y0], "o", color="#c81e1e", ms=7, zorder=5)
    ax.annotate("Drill-01", (X0, Y0), xytext=(X0 - 55, Y0 + 14), fontsize=8, color="#c81e1e")
    if with_barrier:
        ax.plot([X0 + 25, X0 + 25], [Y0 - 60, Y0 + 60], color="black", lw=3, zorder=4, solid_capstyle="butt")
        ax.annotate("barrier 4 m", (X0 + 25, Y0 + 60), xytext=(X0 + 30, Y0 + 66), fontsize=8)
    if with_enclosure:
        ax.add_patch(Rectangle((X0 - 2, Y0 - 3), 4, 6, fill=False, ec=ORANGE, lw=2, zorder=4))   # 4 m (E-W) x 6 m (N-S)


def level_map(ax, a, ext, title, with_barrier=False, with_enclosure=False):
    im = ax.imshow(a, extent=ext, cmap="YlOrRd", vmin=35, vmax=75, origin="upper", interpolation="nearest")
    cs = ax.contour(np.linspace(ext[0], ext[1], a.shape[1]), np.linspace(ext[3], ext[2], a.shape[0]), a, levels=[55],
                    colors=[NAVY], linewidths=1.6)
    ax.clabel(cs, fmt="55 dB(A)", fontsize=7)
    draw_scene(ax, with_barrier, with_enclosure)
    ax.set_title(title, fontsize=10, loc="left", color=NAVY)
    ax.set_xlabel("Easting, ITM (m)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_aspect("equal")
    return im


def main():
    work = sys.argv[1]
    os.makedirs(OUT, exist_ok=True)
    gdb = fresh_gdb(work, "manual")
    bar = barrier(name="Screen", path=[(X0 + 25, Y0 - 60), (X0 + 25, Y0 + 60)], h=4.0)
    enc = enclosure(name="Enclosure", material=MASS_LAW(25.0), h=3.0, length=6.0, width=4.0)
    enc["open_area_m2"] = 0.5          # a ventilation opening: without it the ideal model gives an unrealistic reduction
    runs = {}
    for tag, st in (("A_baseline", []), ("B_barrier", [bar]), ("C_barrier_enclosure", [bar, enc])):
        res = R.run(example(gdb, tag, copy.deepcopy(st)), LOG)
        runs[tag] = res
    A, ext = arr_and_extent(runs["A_baseline"]["created"]["laeq"])
    B, _ = arr_and_extent(runs["B_barrier"]["created"]["laeq"])
    C, _ = arr_and_extent(runs["C_barrier_enclosure"]["created"]["laeq"])

    # ---- 1. three level maps with one shared colour scale
    fig, axs = plt.subplots(1, 3, figsize=(13, 3.9), sharey=True)
    ims = [level_map(axs[0], A, ext, "A  Baseline"),
           level_map(axs[1], B, ext, "B  + 4 m barrier", True),
           level_map(axs[2], C, ext, "C  + barrier + enclosure", True, True)]
    axs[0].set_ylabel("Northing, ITM (m)", fontsize=8)
    cb = fig.colorbar(ims[2], ax=axs, shrink=0.85, pad=0.01)
    cb.set_label("LAeq, dB(A), shared scale", fontsize=8)
    fig.savefig(os.path.join(OUT, "maps_abc.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)

    # ---- 2. what the mitigation did (difference maps)
    fig, axs = plt.subplots(1, 2, figsize=(9, 3.9), sharey=True)
    for ax, (d, ttl) in zip(axs, ((A - B, "Barrier alone (A minus B)"), (B - C, "Enclosure added (B minus C)"))):
        im = ax.imshow(d, extent=ext, cmap="Blues", vmin=0, vmax=max(5, np.nanmax(d)), origin="upper", interpolation="nearest")
        draw_scene(ax, True, d is not None and ttl.startswith("Enclosure"))
        ax.set_title(ttl, fontsize=10, loc="left", color=NAVY)
        ax.set_aspect("equal"); ax.tick_params(labelsize=7); ax.set_xlabel("Easting, ITM (m)", fontsize=8)
        c = fig.colorbar(im, ax=ax, shrink=0.8); c.set_label("reduction, dB", fontsize=8)
    fig.savefig(os.path.join(OUT, "differences.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)

    # ---- 3. spectrum and enclosure effect
    snap = R.read_snapshot(gdb, runs["C_barrier_enclosure"]["run_name"])
    lw_eff = snap["resolved"]["enclosure_Lw_effective"][0]
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    x = np.arange(8)
    ax.bar(x - 0.2, LW_DRILL, 0.4, color=NAVY, label="Source Lw")
    ax.bar(x + 0.2, lw_eff, 0.4, color=ORANGE, label="Radiated Lw with enclosure")
    ax.set_xticks(x); ax.set_xticklabels(["63", "125", "250", "500", "1k", "2k", "4k", "8k"], fontsize=8)
    ax.set_ylabel("dB re 1 pW", fontsize=8); ax.set_xlabel("Octave band, Hz", fontsize=8)
    ax.legend(fontsize=8, frameon=False); ax.tick_params(labelsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.savefig(os.path.join(OUT, "spectrum.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)

    # ---- 4. barrier profile over the DTM
    sc_b = example(gdb, "prof", [bar])
    wkid = SC.analysis_wkid(sc_b)
    win = SC.load_dtm_window(sc_b, (X0 + 20, Y0 - 70, X0 + 30, Y0 + 70), wkid, pad=30.0)
    prof, top = SC.barrier_profile(sc_b, "w1", win)
    s = [p[0] for p in prof]; g = [p[1] for p in prof]; t = [p[2] for p in prof]
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    ax.fill_between(s, [v if v is not None else np.nan for v in g], min(v for v in g if v is not None) - 2, color="#c9b79c")
    ax.plot(s, [v if v is not None else np.nan for v in g], color="#6b4f2a", lw=1.5, label="Ground (DTM)")
    ax.plot(s, t, color=NAVY, lw=2, label="Barrier top (flat top %.1f m)" % top)
    ax.set_xlabel("Distance along the barrier (m)", fontsize=8); ax.set_ylabel("Elevation (m)", fontsize=8)
    ax.legend(fontsize=8, frameon=False, loc="upper right"); ax.tick_params(labelsize=8)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.savefig(os.path.join(OUT, "profile.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)

    # ---- numbers for the text
    nx = A.shape[1]
    def at(a, dx, dy):
        ix = int((X0 + dx - ext[0]) / 5.0); iy = int((ext[3] - (Y0 + dy)) / 5.0)
        return float(a[iy, ix])
    pts = [("R1  60 m east", 60, 0), ("R2  100 m east, 30 m north", 100, 30), ("R3  160 m east, 40 m south", 160, -40)]
    table = [{"name": n, "A": at(A, dx, dy), "B": at(B, dx, dy), "C": at(C, dx, dy)} for n, dx, dy in pts]
    share = lambda a: 100.0 * float(np.nansum(a > 55)) / float(np.isfinite(a).sum())
    info = {"table": table, "share_above_55": {"A": share(A), "B": share(B), "C": share(C)},
            "max": {"A": float(np.nanmax(A)), "B": float(np.nanmax(B)), "C": float(np.nanmax(C))},
            "lw_eff": lw_eff, "lw": LW_DRILL, "cells": int(np.isfinite(A).sum()), "flat_top": top,
            "run_names": {k: v["run_name"] for k, v in runs.items()},
            "engine": snap["engine"]["matlab"]}
    with open(os.path.join(OUT, "figures.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
