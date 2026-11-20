"""Figures and numbers of the worked example, read from the geodatabase of the REAL runs made inside ArcGIS Pro by the
automated example (docs\\capture notes in the manual). Usage: propy docs\\make_example_figures.py <manual_run.gdb>
Writes docs/figures/ui/fig_compare.png, fig_passfail.png and example_numbers.json."""
import json
import os
import re
import sys

import arcpy
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "figures", "ui")
gdb = sys.argv[1]
arcpy.env.workspace = gdb
NAVY = "#1f3b5c"
SRC = (180000.0, 665000.0)
BARRIER = [(180025.0, 664960.0), (180025.0, 665040.0)]
AREA = (179940.0, 664900.0, 180240.0, 665100.0)


def latest(prefix, suffix):
    names = [r for r in arcpy.ListRasters() + arcpy.ListTables() if re.fullmatch(r"%s(_\d+)?_%s" % (prefix, suffix), r)]
    if not names:
        raise SystemExit("no %s_*_%s in %s" % (prefix, suffix, gdb))
    return sorted(names, key=lambda n: int((re.search(r"_(\d+)_%s$" % suffix, n) or [0, 1])[1]) if re.search(r"_(\d+)_%s$" % suffix, n) else 1)[-1]


def arr(name):
    r = arcpy.Raster(os.path.join(gdb, name))
    a = arcpy.RasterToNumPyArray(r).astype(float)
    nd = r.noDataValue
    if nd is not None:
        a[a == nd] = np.nan
    a[np.abs(a) > 1e30] = np.nan
    e = r.extent
    return a, (e.XMin, e.XMax, e.YMin, e.YMax)


def summary(name):
    return {row[0]: (row[1], row[2], row[3]) for row in arcpy.da.SearchCursor(os.path.join(gdb, name), ["Item", "Value", "Unit", "Note"])}


a_name, b_name = latest("A_baseline", "LAeq"), latest("B_barrier", "LAeq")
A, ext = arr(a_name)
B, _ = arr(b_name)
PF, _ = arr(b_name.replace("LAeq", "PassFail"))
MA, _ = arr(b_name.replace("LAeq", "Margin"))
sumA, sumB = summary(a_name.replace("LAeq", "Summary")), summary(b_name.replace("LAeq", "Summary"))
vmin, vmax = 35.0, 75.0


def base(ax, title):
    ax.plot(*SRC, "o", color="#c81e1e", ms=7, zorder=5)
    ax.annotate("Drill-01", SRC, xytext=(SRC[0] - 45, SRC[1] + 12), fontsize=8, color="#c81e1e")
    ax.plot(*zip(*BARRIER), "-", color="black", lw=3, zorder=4)
    ax.set_title(title, fontsize=10, color=NAVY)
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])


fig, axs = plt.subplots(1, 3, figsize=(13, 4.0), constrained_layout=True)
for ax, data, t in ((axs[0], A, "A: without the barrier  (LAeq, dB(A))"), (axs[1], B, "B: with the 4 m barrier  (LAeq, dB(A))")):
    im = ax.imshow(data, extent=ext, cmap="RdYlGn_r", vmin=vmin, vmax=vmax, origin="upper")
    c = ax.contour(np.linspace(ext[0], ext[1], data.shape[1]), np.linspace(ext[3], ext[2], data.shape[0]), data, levels=[55], colors="k", linewidths=1.2)
    base(ax, t)
fig.colorbar(im, ax=axs[:2], shrink=0.85, label="dB(A)")
d = B - A
im3 = axs[2].imshow(d, extent=ext, cmap="PuOr", vmin=-12, vmax=12, origin="upper")
base(axs[2], "B minus A  (dB): the effect of the barrier")
fig.colorbar(im3, ax=axs[2], shrink=0.85, label="dB")
fig.savefig(os.path.join(OUT, "fig_compare.png"), dpi=150)
plt.close(fig)

fig, axs = plt.subplots(1, 2, figsize=(9.5, 4.0), constrained_layout=True)
cm = matplotlib.colors.ListedColormap(["#b42318", "#2e7d32"])
axs[0].imshow(PF, extent=ext, cmap=cm, vmin=0, vmax=1, origin="upper")
base(axs[0], "PASS (green) / FAIL (red): every limit must be met")
im = axs[1].imshow(MA, extent=ext, cmap="RdBu_r", vmin=-20, vmax=20, origin="upper")
base(axs[1], "Margin: largest exceedance of any limit (dB)")
fig.colorbar(im, ax=axs[1], shrink=0.85, label="dB, positive = exceeds")
fig.savefig(os.path.join(OUT, "fig_passfail.png"), dpi=150)
plt.close(fig)

nums = {"runs": [a_name, b_name], "A": {"min": float(np.nanmin(A)), "max": float(np.nanmax(A)), "mean": float(np.nanmean(A))},
        "B": {"min": float(np.nanmin(B)), "max": float(np.nanmax(B)), "mean": float(np.nanmean(B))},
        "largest_reduction_dB": float(np.nanmin(d)), "mean_change_dB": float(np.nanmean(d)),
        "share_above_55_A": float(np.nanmean(A > 55) * 100), "share_above_55_B": float(np.nanmean(B > 55) * 100),
        "summary_A": {k: v[0] for k, v in sumA.items() if v[0] is not None}, "summary_B": {k: v[0] for k, v in sumB.items() if v[0] is not None},
        "cells": int(np.isfinite(A).sum())}
json.dump(nums, open(os.path.join(OUT, "example_numbers.json"), "w", encoding="utf-8"), indent=1)
print(json.dumps({k: nums[k] for k in ("runs", "A", "B", "largest_reduction_dB", "share_above_55_A", "share_above_55_B")}, indent=1))
