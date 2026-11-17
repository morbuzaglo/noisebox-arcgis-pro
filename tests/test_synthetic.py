"""Synthetic-scene test (propy):  one source, one barrier, flat ground, limits, detail cells.

1. Runs the toolbox pipeline (the same code the .pyt calls): LAeq, per-band rasters, margin / pass-fail,
   noise bands, detail cells.
2. Runs run_acoustic_case directly (Python 3.10 env) for every cell with hand-built barrier geometry.
3. Compares LAeq, every band, and every detail-cell field (Adiv/Aatm/Agr/Abar per band, margins, status).
Usage: propy tests\\test_synthetic.py [outdir]
"""
import json
import subprocess
import sys
import tempfile

import numpy as np

from common import *  # noqa: F401,F403
from noisebox import config, pipeline

OVERALL = 45.0
BAND_LIM = [None, None, None, 40.0, None, None, None, None]     # 500 Hz band limited to 40 dB (unweighted)


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="nb_test_")
    gdb = fresh_gdb(outdir, "syn")
    p = scene(gdb, "syn", bands=True, detail="Full", iso_step=5, copy_inputs=True,
              overall=OVERALL, band_limits=BAND_LIM)
    created = pipeline.sources_to_raster(p, pipeline.PrintLog())
    print("\nCreated:", sorted(created))

    la = raster(created["laeq"])                                          # row 0 = top
    ras = arcpy.Raster(created["laeq"])
    cs = ras.meanCellWidth
    ny, nx = la.shape
    cells = []
    for iy in range(ny):
        for ix in range(nx):
            x = ras.extent.XMin + (ix + 0.5) * cs
            y = ras.extent.YMax - (iy + 0.5) * cs
            cells.append({"x": x, "y": y, "iy": iy, "ix": ix, "raster": float(la[iy, ix])})
    job = {"core_dir": config.core_dir(), "hr": p["hr"], "G": p["G"], "T": p["T"], "RH": p["RH"], "mode": p["mode"],
           "source": {"x": X0, "y": Y0, "h": 1.0, "Lw": LW},
           "barrier": {"x1": X0 + 20.0, "x2": X0 + 20.5, "h": 4.0},
           "receivers": [{"x": c["x"], "y": c["y"]} for c in cells]}
    jin, jout = os.path.join(outdir, "direct_in.json"), os.path.join(outdir, "direct_out.json")
    with open(jin, "w", encoding="utf-8") as f:
        json.dump(job, f)
    subprocess.run([config.find_python310(), os.path.join(ROOT, "tests", "direct_core.py"), jin, jout], check=True,
                   env=config.clean_env())
    with open(jout, "r", encoding="utf-8") as f:
        ref = json.load(f)
    ok = True

    def check(name, diff, tol=1e-4):
        nonlocal ok
        m = float(np.nanmax(np.abs(diff)))
        good = m < tol
        ok &= good
        print("  %-42s max |diff| = %.2e dB  %s" % (name, m, "ok" if good else "<-- MISMATCH"))

    print("\nCells compared: %d" % len(cells))
    check("LAeq raster vs run_acoustic_case", [c["raster"] - r["LpA"] for c, r in zip(cells, ref)])
    for i, b in enumerate(config.BANDS):
        arr = raster(created["Lp%d" % b])
        check("Lp %d Hz raster" % b, [arr[c["iy"], c["ix"]] - r["Lp_bands"][i] for c, r in zip(cells, ref)])

    # detail cells: attributes must equal the direct terms
    flds = ["SHAPE@XY", "LAeq", "Status", "Margin_dBA", "Worst_Hz", "Worst_dB", "PathType", "DomSrc", "Dist_m"] + \
           ["%s_%d" % (k, b) for k in ("Lp", "LpA", "Adiv", "Aatm", "Agr", "Abar", "Marg") for b in config.BANDS]
    ref_by = {(round(c["x"], 1), round(c["y"], 1)): r for c, r in zip(cells, ref)}
    diffs = {k: [] for k in ("LAeq", "Lp", "LpA", "Adiv", "Aatm", "Agr", "Abar", "Dist", "Margin")}
    statuses = []
    with arcpy.da.SearchCursor(created["cells"], flds) as cur:
        for row in cur:
            r = ref_by[(round(row[0][0], 1), round(row[0][1], 1))]
            d = dict(zip(flds, row))
            diffs["LAeq"].append(d["LAeq"] - r["LpA"])
            diffs["Dist"].append(d["Dist_m"] - r["d"])
            diffs["Margin"].append(d["Margin_dBA"] - (r["LpA"] - OVERALL))
            for k, key in (("Lp", "Lp_bands"), ("LpA", "LpA_bands"), ("Adiv", "Adiv"), ("Aatm", "Aatm"),
                           ("Agr", "Agr"), ("Abar", "Abar")):
                for i, b in enumerate(config.BANDS):
                    diffs[k].append(d["%s_%d" % (k, b)] - r[key][i])
            lim_fail = r["LpA"] > OVERALL or r["Lp_bands"][3] > 40.0
            statuses.append((d["Status"] == "FAIL") == lim_fail)
            mb = d["Marg_500"] - (r["Lp_bands"][3] - 40.0)
            diffs["Margin"].append(mb)
    print("Detail cells read: %d" % len(statuses))
    for k, v in diffs.items():
        check("cell field group %s" % k, v)
    print("  Status field consistent with limits (overall 45 dB(A), 500 Hz 40 dB): %s" % all(statuses))
    ok &= all(statuses)
    pf = raster(created["passfail"])
    npf = int(np.nansum(pf == 0))
    print("  PassFail raster: %d FAIL cells, %d PASS cells" % (npf, int(np.nansum(pf == 1))))
    nb = int(arcpy.management.GetCount(created["bands"]).getOutput(0))
    print("  Noise-band polygons: %d" % nb)
    print("  Summary table rows:", int(arcpy.management.GetCount(created["summary"]).getOutput(0)))
    print("\nRESULT:", "PASS" if ok else "MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
