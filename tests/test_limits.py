"""Allowed levels (propy, needs MATLAB): overall dB(A) limit, per-band limits, and the rule "one exceeded limit = FAIL".
Usage: propy tests\\test_limits.py <outdir>
"""
import copy
import sys

import numpy as np

from common import *  # noqa: F401,F403
from scn_common import *  # noqa: F401,F403
from noisebox import pipeline, scenario as SC, scenario_run as R
from noisebox import issues as I
from noisebox.config import BANDS

LOG = pipeline.PrintLog()
RESULTS = []


def report(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("RESULT %-72s %s %s" % (name, "PASS" if ok else "FAIL", detail))


def run(sc, tag, **out):
    s = copy.deepcopy(sc)
    s["outputs"].update(out)
    s["outputs"]["run_name"] = tag
    return R.run(s, LOG)


def read_cells(path):
    import arcpy
    rows = {}
    want = (["gridcode", "Status", "Margin_dBA", "Worst_Hz", "Worst_dB"] + ["Marg_%d" % b for b in BANDS]
            + ["LpA_%d" % b for b in BANDS] + ["LAeq"])
    have = {f.name for f in arcpy.ListFields(path)}
    use = [w for w in want if w in have]
    with arcpy.da.SearchCursor(path, use) as cur:
        for r in cur:
            d = dict(zip(use, r))
            rows[d["gridcode"]] = tuple(d.get(w) for w in want)       # columns missing in the table read as None
    return rows


def main():
    outdir = sys.argv[1]
    gdb = fresh_gdb(outdir, "limits")
    base = base_scenario(gdb)
    base["outputs"].update({"detail": "Full", "overall_a": True})

    print("=== 1. scenario fields and validation ===")
    o = base["outputs"]
    report("new scenarios carry limit_bands (8 x None) and limit_band_weighting 'A'",
           o.get("limit_bands") == [None] * 8 and o.get("limit_band_weighting") == "A")
    bad = copy.deepcopy(base); bad["outputs"]["limit_bands"] = [None, "x", None, None, None, None, None, None]
    report("a non-number band limit is OUT-021", "OUT-021" in codes(bad))
    bad = copy.deepcopy(base); bad["outputs"]["limit_bands"] = [1, 2, 3]
    report("a band-limit list that is not 8 long is OUT-020", "OUT-020" in codes(bad))
    bad = copy.deepcopy(base); bad["outputs"]["limit_band_weighting"] = "C"
    report("an unknown weighting is OUT-022", "OUT-022" in codes(bad))
    ok = copy.deepcopy(base); ok["outputs"]["limit_bands"] = [None, None, None, 40.0, None, None, None, None]
    report("a valid band limit validates and says the pass rule (OUT-023)", "OUT-023" in codes(ok) and not I.has_errors(SC.validate(ok)))
    report("limits_set / limit_rule_text", SC.limits_set(ok["outputs"]) and "500 Hz <= 40" in SC.limit_rule_text(ok["outputs"]))
    report("no limit -> limits_set False", not SC.limits_set(base["outputs"]))
    old = copy.deepcopy(base); del old["outputs"]["limit_bands"]; del old["outputs"]["limit_band_weighting"]
    report("an older scenario without band-limit fields still validates", not I.has_errors(SC.validate(old)))

    print("=== 2. overall limit only ===")
    b0 = read_cells(run(base, "lim_none")["created"]["cells"])
    i500 = BANDS.index(500)
    L_OV = float(np.median([r[-1] for r in b0.values()]))                  # thresholds taken from the data so that some
    L_B500 = float(np.median([r[13 + i500] for r in b0.values()]))          # cells pass and some fail
    L_TOP = float(max(r[-1] for r in b0.values())) + 5.0
    print("  thresholds from the baseline: overall %.1f dB(A), 500 Hz %.1f dB(A), top %.1f" % (L_OV, L_B500, L_TOP))
    ov = run(base, "lim_overall", limit_dba=L_OV)
    cells = read_cells(ov["created"]["cells"])
    bad_rule = [k for k, r in cells.items() if (r[1] == "FAIL") != (r[-1] > L_OV)]
    report("overall limit: FAIL exactly where LAeq > its limit", not bad_rule and any(r[1] == "FAIL" for r in cells.values())
           and any(r[1] == "PASS" for r in cells.values()), "%d cells, %d fail" % (len(cells), sum(r[1] == "FAIL" for r in cells.values())))

    print("=== 3. one band limit only ===")
    lb = [None] * 8
    lb[3] = L_B500                                                  # 500 Hz, dB(A) per band
    bd = run(base, "lim_band", limit_bands=lb)
    cells = read_cells(bd["created"]["cells"])
    i500 = BANDS.index(500)
    # columns: 0 id, 1 status, 2 margin, 3 worstHz, 4 worstdB, 5..12 Marg_*, 13..20 LpA_*, 21 LAeq
    wrong = [k for k, r in cells.items() if (r[1] == "FAIL") != (r[13 + i500] > L_B500)]
    report("band limit 500 Hz: FAIL exactly where LpA_500 > limit", not wrong and any(r[1] == "FAIL" for r in cells.values())
           and any(r[1] == "PASS" for r in cells.values()), "%d cells" % len(cells))
    mg = [abs(r[5 + i500] - (r[13 + i500] - L_B500)) for r in cells.values()]
    report("Marg_500 = LpA_500 - limit", max(mg) < 1e-6, "max |err| %.2e" % max(mg))
    report("other bands have no margin (no limit set)", all(r[5 + BANDS.index(125)] is None for r in cells.values()))
    report("Worst_Hz is 500 where the band fails", all((r[3] == 500) for r in cells.values() if r[1] == "FAIL"))

    print("=== 4. overall passes, but one band exceeds -> FAIL ===")
    comb = copy.deepcopy(lb)
    cb = run(base, "lim_comb", limit_dba=L_TOP, limit_bands=comb)    # overall never exceeded; band 500 is
    cells = read_cells(cb["created"]["cells"])
    over_ok = all(r[-1] <= L_TOP for r in cells.values())
    fails = [r for r in cells.values() if r[1] == "FAIL"]
    report("every cell is under the (high) overall limit", over_ok)
    report("cells still FAIL because of the 500 Hz band", len(fails) > 0 and all(r[13 + i500] > L_B500 for r in fails),
           "%d FAIL cells" % len(fails))
    m_ras = raster(cb["created"]["margin"])
    cid = {k: r for k, r in cells.items()}
    report("Margin raster = largest exceedance over all limits (max 500 Hz margin)",
           abs(np.nanmax(m_ras) - max(r[5 + i500] for r in cells.values())) < 1e-4, "max %.2f dB" % np.nanmax(m_ras))

    print("=== 5. both limits tight: FAIL if either fails ===")
    both = run(base, "lim_both", limit_dba=L_OV - 1.0, limit_bands=comb)
    cells = read_cells(both["created"]["cells"])
    wrong = [k for k, r in cells.items() if (r[1] == "FAIL") != (r[-1] > L_OV - 1.0 or r[13 + i500] > L_B500)]
    report("FAIL exactly where LAeq > overall OR LpA_500 > band limit", not wrong, "%d cells" % len(cells))

    print("=== 6. unweighted (Z) comparison of band limits ===")
    z = run(base, "lim_z", limit_bands=[None, None, None, 70.0, None, None, None, None], limit_band_weighting="Z")
    cells_z = read_cells(z["created"]["cells"])
    import arcpy
    lp = {}
    with arcpy.da.SearchCursor(z["created"]["cells"], ["gridcode", "Lp_500", "Marg_500"]) as cur:
        for r in cur:
            lp[r[0]] = r
    report("weighting Z: Marg_500 = Lp_500 (unweighted) - limit", max(abs(r[2] - (r[1] - 70.0)) for r in lp.values()) < 1e-6)

    print("=== 7. summary table lists every limit ===")
    rows = [r[0] for r in arcpy.da.SearchCursor(both["created"]["summary"], ["Item"])] if "Item" in [f.name for f in arcpy.ListFields(both["created"]["summary"])] else []
    txt = " ".join(str(r) for r in arcpy.da.SearchCursor(both["created"]["summary"], ["*"]))
    report("Summary names the overall limit, the 500 Hz limit and the pass rule",
           "Limit, overall" in txt and "Limit, 500 Hz" in txt and "Pass rule" in txt)
    print("\nRESULT: %s" % ("PASS" if all(RESULTS) else "FAIL"))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
