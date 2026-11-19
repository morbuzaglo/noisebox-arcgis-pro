"""Scenario runs through the MATLAB core (propy; needs the Python 3.10 worker). Usage: propy tests\\test_scenario_engine.py <outdir>

Checks: baseline == original toolbox; barrier / enclosure on-off; hidden vs excluded; Dc, C0, separate G; band-selection
independence; unweighted sum; material and atmosphere previews; snapshot reproducibility.
"""
import copy
import json
import math
import os
import subprocess
import sys

import numpy as np

from common import *  # noqa: F401,F403
from scn_common import *  # noqa: F401,F403
from noisebox import config, pipeline, scenario as SC, scenario_run as R
from noisebox.config import BANDS

LOG = pipeline.PrintLog()
RESULTS = []


def report(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("RESULT %-66s %s %s" % (name, "PASS" if ok else "FAIL", detail))


def run(sc, tag):
    s = copy.deepcopy(sc)
    s["outputs"]["run_name"] = tag
    res = R.run(s, LOG)
    return res


def ras(res, key="laeq"):
    return raster(res["created"][key])


def direct_matlab(expr, outdir):
    """Evaluate a MATLAB expression through the core with a fresh engine (py3.10) and return its JSON result."""
    py = config.find_python310()
    code = (
        "import json,sys,matlab.engine\n"
        "e=matlab.engine.start_matlab()\n"
        "e.addpath(%r,nargout=0)\n"
        "r=e.eval(%r,nargout=1)\n"
        "print('JSON'+json.dumps(r))\n" % (config.core_dir(), "jsonencode(" + expr + ")"))
    p = subprocess.run([py, "-c", code], capture_output=True, text=True, env=config.clean_env(), cwd=outdir)
    line = [ln for ln in p.stdout.splitlines() if ln.startswith("JSON")]
    if not line:
        raise RuntimeError("MATLAB direct call failed:\n" + p.stdout[-500:] + p.stderr[-800:])
    return json.loads(json.loads(line[0][4:]))


def main():
    outdir = sys.argv[1]
    gdb = fresh_gdb(outdir, "scn_engine")
    base = base_scenario(gdb)

    print("=== 1. Baseline: new interface == original toolbox (same inputs) ===")
    sc = copy.deepcopy(base)
    sc["structures"] = [building()]                       # the sample wall as a footprint polygon, 4 m
    new = ras(run(sc, "n_base"))
    old = raster(pipeline.sources_to_raster(scene(gdb, "o_base"), LOG)["laeq"])
    d = float(np.nanmax(np.abs(new - old)))
    report("LAeq raster identical to the original NoiseMap tool", d < 1e-9 and new.shape == old.shape,
           "max |diff| %.2e dB, %s cells" % (d, new.size))
    flat = ras(run(base, "n_flat"))
    report("without the wall the levels are higher behind it", np.nanmax(flat - new) > 3, "up to %.1f dB" % np.nanmax(flat - new))

    print("\n=== 2. Barrier on / off, hidden vs excluded ===")
    sc = copy.deepcopy(base); sc["structures"] = [barrier(h=4.0)]
    on = ras(run(sc, "bar_on"))
    sc = copy.deepcopy(base); sc["structures"] = [barrier(h=4.0, include=False)]
    off = ras(run(sc, "bar_off"))
    sc = copy.deepcopy(base); sc["structures"] = [barrier(h=4.0, visible=False)]
    hid = ras(run(sc, "bar_hidden"))
    report("barrier on lowers the receiver levels", np.nanmax(flat - on) > 3 and np.nanmin(flat - on) > -1e-6,
           "up to %.1f dB" % np.nanmax(flat - on))
    report("barrier off restores the baseline exactly", float(np.nanmax(np.abs(off - flat))) < 1e-9)
    report("hiding the drawing leaves the result unchanged", float(np.nanmax(np.abs(hid - on))) < 1e-9)
    sc = copy.deepcopy(base); sc["structures"] = [barrier(h=4.0, mode="absolute")]
    ab = ras(run(sc, "bar_abs"))
    report("absolute top 4 m on flat ground == relative 4 m", float(np.nanmax(np.abs(ab - on))) < 1e-9)
    sc = copy.deepcopy(base)
    b = barrier(h=4.0); b["placement"] = {"mode": "straight", "start": [X0 + 20, Y0 - 100], "length_m": 200.0, "azimuth_deg": 0.0}
    b["path"] = None; sc["structures"] = [b]
    st = ras(run(sc, "bar_straight"))
    report("straight barrier from start/length/azimuth == the drawn polyline", float(np.nanmax(np.abs(st - on))) < 1e-9)
    tr = barrier(h=4.0, transmission={"enabled": True, "material": MASS_LAW(25.0)})
    sc = copy.deepcopy(base); sc["structures"] = [tr]
    wt = ras(run(sc, "bar_trans"))
    report("transmission adds energy behind a barrier (never lowers it)", np.nanmin(wt - on) > -1e-6 and np.nanmax(wt - on) > 0.0,
           "up to +%.2f dB vs diffraction only" % np.nanmax(wt - on))

    print("\n=== 3. Enclosure on / off ===")
    mat = MANUF([20, 22, 24, 26, 28, 30, 32, 34], [0.5] * 8)
    sc = copy.deepcopy(base); sc["structures"] = [enclosure(material=mat)]
    r_on = run(sc, "enc_on")
    on_e = ras(r_on)
    sc = copy.deepcopy(base); sc["structures"] = [enclosure(material=mat, include=False)]
    off_e = ras(run(sc, "enc_off"))
    report("enclosure on lowers every receiver", np.nanmax(on_e - flat) < -3, "by %.1f to %.1f dB" % (np.nanmin(flat - on_e), np.nanmax(flat - on_e)))
    report("enclosure off restores the baseline exactly", float(np.nanmax(np.abs(off_e - flat))) < 1e-9)
    sc = copy.deepcopy(base); e = enclosure(material=mat, visible=False); sc["structures"] = [e]
    hid_e = ras(run(sc, "enc_hidden"))
    report("hiding the enclosure drawing leaves the result unchanged", float(np.nanmax(np.abs(hid_e - on_e))) < 1e-9)

    print("\n=== 4. Enclosure physics: composite surfaces vs the core's own nb_enclosure ===")
    S_tot = 2 * (6 + 4) * 3.0 + 24.0
    tl = [20, 22, 24, 26, 28, 30, 32, 34]
    expr = ("nb_enclosure(%s, struct('S_total',%g,'A_in',%g,'mat',struct('TL',%s),'S_open',0))" %
            ("[100 100 100 100 100 95 90 85]", S_tot, 0.5 * S_tot, "[20 22 24 26 28 30 32 34]"))
    direct = direct_matlab(expr, outdir)
    glue_lw = None
    lw_eff = r_on["engine"]  # fingerprint info only
    # recompute through the glue result stored in the snapshot
    snap = R.read_snapshot(gdb, r_on["run_name"])
    glue_lw = snap["resolved"]["enclosure_Lw_effective"][0]
    err = max(abs(a - b) for a, b in zip(glue_lw, direct["Lw_out"]))
    report("single-material enclosure: radiated Lw equals nb_enclosure (core, unmodified)", err < 1e-9,
           "max |diff| %.1e dB; Lw_out %s" % (err, ["%.1f" % v for v in glue_lw]))
    # two different materials: area-weighted composite checked against an independent hand calculation
    wallN = MANUF([20] * 8, [0.4] * 8)
    roof = MANUF([40] * 8, [0.8] * 8)
    sc = copy.deepcopy(base)
    e = enclosure(); e["faces"] = {"mode": "per_face", "all": None, "faces": {"Wall N": wallN, "Wall E": wallN, "Wall S": wallN, "Wall W": wallN, "Roof": roof}}
    sc["structures"] = [e]
    r_c = run(sc, "enc_comp")
    lw_c = R.read_snapshot(gdb, r_c["run_name"])["resolved"]["enclosure_Lw_effective"][0]
    walls, rf = 2 * (6 + 4) * 3.0, 24.0
    S = walls + rf
    tau = (walls * 10 ** (-20 / 10.0) + rf * 10 ** (-40 / 10.0)) / S
    TLc = -10 * math.log10(tau)
    A = walls * 0.4 + rf * 0.8
    exp_lw = [lw + 10 * math.log10(4 / A) - TLc + 10 * math.log10(S) - 6 for lw in BAND_LW]   # nb_enclosure formulas, by hand
    err2 = max(abs(a - b) for a, b in zip(lw_c, exp_lw))
    report("two materials: composite TL and absorption area match an independent hand calculation", err2 < 1e-9,
           "max |diff| %.1e dB" % err2)

    print("\n=== 5. Other propagation inputs ===")
    dc = copy.deepcopy(base); dc["source"]["directivity"] = {"mode": "directional", "dc": [3.0] * 8, "heading_deg": 0.0, "angular_table": None}
    d3 = ras(run(dc, "dc3"))
    report("directivity Dc = +3 dB in all bands raises every level by 3.000 dB", float(np.nanmax(np.abs((d3 - flat) - 3.0))) < 1e-4,
           "dev %.1e" % np.nanmax(np.abs((d3 - flat) - 3.0)))
    lt = copy.deepcopy(base); lt["propagation"]["meteorology"] = {"method": "long_term", "C0": 3.0}
    l3 = ras(run(lt, "c0"))
    dd = flat - l3
    report("long-term C0 = 3 dB lowers levels by between 0 and 3 dB (never raises)", np.nanmin(dd) > -1e-9 and np.nanmax(dd) <= 3.0 + 1e-9,
           "reduction %.2f to %.2f dB" % (np.nanmin(dd), np.nanmax(dd)))
    sg = copy.deepcopy(base); sg["propagation"]["ground"] = {"G": 0.5, "separate": True, "Gs": 0.5, "Gm": 0.5, "Gr": 0.5, "mapped": None}
    gs = ras(run(sg, "gsep"))
    report("separate Gs = Gm = Gr = 0.5 equals uniform G = 0.5", float(np.nanmax(np.abs(gs - flat))) < 1e-9)
    hard = copy.deepcopy(base); hard["propagation"]["ground"]["G"] = 0.0
    hd = ras(run(hard, "g0"))
    report("changing G changes the result (hard ground differs from G = 0.5)", float(np.nanmax(np.abs(hd - flat))) > 0.1)

    print("\n=== 6. Outputs ===")
    allb = copy.deepcopy(base); allb["outputs"]["bands"] = list(BANDS); allb["outputs"]["overall_z"] = True
    ra = run(allb, "allb")
    one = copy.deepcopy(base); one["outputs"]["bands"] = [1000]
    r1 = run(one, "one")
    report("choosing which band rasters to save does not change the overall LAeq", float(np.nanmax(np.abs(ras(ra) - ras(r1)))) < 1e-9)
    report("only the chosen band rasters are written", "Lp1000" in r1["created"] and "Lp63" not in r1["created"]
           and all(("Lp%d" % b) in ra["created"] for b in BANDS))
    bands = np.stack([raster(ra["created"]["Lp%d" % b]) for b in BANDS])
    lz = 10 * np.log10(np.nansum(10 ** (bands / 10.0), axis=0))
    lz[np.all(np.isnan(bands), axis=0)] = np.nan
    dz = float(np.nanmax(np.abs(lz - ras(ra, "lz"))))
    report("unweighted LZ = energy sum of the 8 octave-band rasters", dz < 1e-3, "max |diff| %.1e dB (float32 storage)" % dz)
    report("A-weighted and unweighted overall differ (they are different quantities)", float(np.nanmax(np.abs(ras(ra, "lz") - ras(ra)))) > 0.5)

    print("\n=== 7. Material and atmosphere previews (core) ===")
    mp = R.material_preview(MASS_LAW(20.0))
    expected = [20 * math.log10(f * 20.0) - 20 * math.log10(415 / math.pi) for f in BANDS]
    report("mass-law TL from the core: 20 kg/m2, 1000 Hz = %.1f dB" % expected[4], all(abs(a - max(b, 0)) < 1e-6 for a, b in zip(mp["TL"], expected))
           and mp["source"].startswith("mass-law"), "TL %s" % ["%.1f" % v for v in mp["TL"]])
    ap = R.atmosphere_preview(base)
    al = ap["alpha_dB_per_km"]
    report("atmospheric absorption alpha (dB/km) rises with frequency", all(al[i] < al[i + 1] for i in range(7)),
           ["%.2f" % v for v in al])

    print("\n=== 8. Snapshot reproducibility ===")
    sc = copy.deepcopy(base); sc["structures"] = [barrier(h=4.0)]
    rs = run(sc, "snap")
    sc["structures"][0]["vertical"]["value"] = 9.0            # later edit of the scenario
    snap = R.read_snapshot(gdb, rs["run_name"])
    report("snapshot keeps the settings as they were at the run",
           snap["scenario"]["structures"][0]["vertical"]["value"] == 4.0 and snap["scenario"]["source"]["spectrum"]["lw"] == BAND_LW
           and snap["engine"]["fingerprint_match"] is True, "MATLAB %s" % snap["engine"]["matlab"])
    sc2 = snap["scenario"]
    sc2["outputs"]["run_name"] = "snap_again"
    again = ras(R.run(sc2, LOG))
    report("re-running the snapshot reproduces the earlier raster", float(np.nanmax(np.abs(again - ras(rs)))) < 1e-9)

    print("\nALL PASS" if all(RESULTS) else "\nSOME FAILED (%d of %d)" % (RESULTS.count(False), len(RESULTS)))
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
