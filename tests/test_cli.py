"""The command line the add-in calls (propy, no MATLAB): every command must print one parsable JSON document.
Usage: propy tests\\test_cli.py <outdir>"""
import json
import os
import subprocess
import sys

from common import *  # noqa: F401,F403
from scn_common import *  # noqa: F401,F403
from noisebox import scenario as SC

RESULTS = []


def report(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("RESULT %-62s %s %s" % (name, "PASS" if ok else "FAIL", detail))


def cli(*args):
    p = subprocess.run([sys.executable, os.path.join(ROOT, "noisebox_cli.py")] + [str(a) for a in args],
                       capture_output=True, text=True, cwd=ROOT)
    lines = [ln for ln in p.stdout.splitlines() if ln.startswith("{")]
    if not lines:
        raise RuntimeError("no JSON from %s:\n%s\n%s" % (args, p.stdout[-400:], p.stderr[-600:]))
    return json.loads(lines[-1]), p.returncode


def main():
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    gdb = fresh_gdb(outdir, "cli")

    r, rc = cli("new", os.path.join(outdir, "n.json"), "--name", "From CLI")
    sc, iss = SC.load(os.path.join(outdir, "n.json"))
    report("new creates a loadable scenario", r["ok"] and sc and sc["name"] == "From CLI")

    r, rc = cli("validate", os.path.join(outdir, "n.json"), "--fast")
    codes = {i["code"] for i in r["issues"]}
    report("an empty scenario lists what is missing, with fixes", not r["ok"] and rc == 1
           and {"SRC-001", "SRC-014", "SPC-001", "ARA-001", "OUT-001", "OUT-005"} <= codes
           and all(i["fix"] for i in r["issues"] if i["severity"] == "error"),
           "%d errors, %d warnings" % (r["counts"]["error"], r["counts"]["warning"]))
    report("every issue says which pane section to open", all(i["section"] for i in r["issues"]))

    s = base_scenario(gdb)
    s["structures"] = [barrier(), enclosure()]
    p = SC.save(s, os.path.join(outdir, "ok.json"))
    r, rc = cli("preview", p, "--fast")
    report("preview of a valid scenario: ok, source/area/grid/structures present", r["ok"] and rc == 0 and r["source"]["x"] == X0
           and r["grid"]["cells"] == 60 and len(r["structures"]) == 2, "grid %s" % r["grid"])
    enc = next(x for x in r["structures"] if x["type"] == "enclosure")
    report("preview gives enclosure faces with data state (missing alpha/TL shown)", len(enc["faces"]) == 5
           and all(f["data"] in ("missing", "estimated", "measured") for f in enc["faces"]), [f["data"] for f in enc["faces"]])
    bar = next(x for x in r["structures"] if x["type"] == "barrier")
    report("preview gives the barrier path and length", abs(bar["length_m"] - 200.0) < 1e-9)

    r, rc = cli("parse-spectrum", "--text", "90\t91\t92\t93\t94\t95\t96\t97")
    report("parse-spectrum", r["ok"] and r["lw"][0] == 90)
    r, rc = cli("crs", 4326)
    report("crs labels", r["label_x"] == "Longitude" and r["label_y"] == "Latitude")
    r, rc = cli("suggest-crs", 34.78, 32.08)
    report("suggest-crs for Tel Aviv = Israeli TM Grid", r["wkid"] == 2039)
    r, rc = cli("dtm-info", DEM_SAMPLE)
    report("dtm-info: cell, CRS, unit state", r["ok"] and abs(r["cell_m"] - 30.0) < 1.0 and r["crs_type"] == "Projected",
           "cell %.1f m, unit known: %s" % (r["cell_m"], r["unit_known"]))
    r, rc = cli("validate", os.path.join(outdir, "gone.json"))
    report("missing scenario file is reported as JSON (SCN-001)", not r["ok"] and r["issues"][0]["code"] == "SCN-001")

    # DTM present, unit not set: the explicit prompt (DTM-006) must appear
    s2 = base_scenario(gdb, dtm=DEM_SAMPLE)
    s2["terrain"]["vertical_unit"] = None
    s2["source"].update(SC.source_from_coords(X0, Y0, 2039))
    r, rc = cli("validate", SC.save(s2, os.path.join(outdir, "dtm.json")))
    codes = {i["code"] for i in r["issues"]}
    report("DTM without a stated vertical unit asks for it (DTM-006)", "DTM-006" in codes or "DTM-007" in codes,
           "DTM-006 %s (the sample GeoTIFF may carry a unit)" % ("DTM-006" in codes))
    s2["terrain"]["vertical_unit"] = "m"
    r, rc = cli("preview", SC.save(s2, os.path.join(outdir, "dtm2.json")))
    cov = r.get("coverage") or {}
    report("deep preview reads the DTM: source ground elevation and coverage", r.get("elevation") is not None
           and cov.get("source_status") == "ok", "ground %.1f m, %.1f %% of the area missing" % (
               r["elevation"]["ground_m"], cov.get("pct_area_missing", -1)))
    sc3 = copy_with(s2)
    sc3["source"]["x"], sc3["source"]["y"] = X0 + 5000.0, Y0 + 5000.0             # far outside the 1 km DTM
    r, rc = cli("preview", SC.save(sc3, os.path.join(outdir, "far.json")))
    codes = {i["code"] for i in r["issues"]}
    report("source outside the DTM: precise message (DTM-008) and the run is blocked", "DTM-008" in codes and not r["ok"])

    print("\nALL PASS" if all(RESULTS) else "\nSOME FAILED (%d of %d)" % (RESULTS.count(False), len(RESULTS)))
    return 0 if all(RESULTS) else 1


def copy_with(sc):
    import copy
    return copy.deepcopy(sc)


if __name__ == "__main__":
    sys.exit(main())
