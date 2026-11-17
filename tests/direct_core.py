"""Direct run_acoustic_case reference for the synthetic scene. Run with the Python 3.10 MATLAB-Engine env.

Usage: python direct_core.py <in.json> <out.json>
Computes, for every receiver, the single-source / single-receiver result with hand-built barrier geometry
(thin wall, two top edges) straight from run_acoustic_case, independent of run_field_3d and of the glue.
"""
import json
import math
import sys

import matlab.engine


def main(inp, outp):
    with open(inp, "r", encoding="utf-8") as f:
        J = json.load(f)
    eng = matlab.engine.start_matlab()
    eng.addpath(J["core_dir"], nargout=0)
    s = J["source"]
    bar = J.get("barrier")
    res = []
    for r in J["receivers"]:
        dx, dy = r["x"] - s["x"], r["y"] - s["y"]
        dp = math.hypot(dx, dy)
        c = {"Lw": matlab.double(s["Lw"]), "hs": s["h"], "hr": J["hr"], "dp": dp, "dh": 0.0,
             "G": {"Gs": J["G"], "Gm": J["G"], "Gr": J["G"]},
             "atm": {"T_C": J["T"], "RH": J["RH"], "p_kPa": 101.325}, "mode": J["mode"]}
        o0 = eng.run_acoustic_case(c)
        entry = {"x": r["x"], "y": r["y"], "free_LpA": o0["LpA_broadband"]}
        o = o0
        if bar:
            # wall planes x = x1 (near face) and x2 (far face), top at absolute height H (flat ground = 0)
            a1 = dp * (bar["x1"] - s["x"]) / dx
            a2 = dp * (bar["x2"] - s["x"]) / dx
            H = bar["h"]
            d = math.sqrt(dp ** 2 + (J["hr"] - s["h"]) ** 2)
            dss = math.hypot(a1, H - s["h"])
            e = a2 - a1
            dsr = math.hypot(dp - a2, H - J["hr"])
            z = dss + e + dsr - d
            c2 = dict(c)
            c2["barrier"] = {"z": z, "dss": dss, "dsr": dsr, "e": e}
            o = eng.run_acoustic_case(c2)
            entry["z"] = z
        row = lambda k: [float(v) for v in o[k][0]]          # noqa: E731
        entry.update({"LpA": o["LpA_broadband"], "Lp_bands": row("Lp"), "LpA_bands": row("LpA_bands"),
                      "Adiv": row("Adiv"), "Aatm": row("Aatm"), "Agr": row("Agr"), "Abar": row("Abar"),
                      "d": float(o["d"])})
        res.append(entry)
    eng.quit()
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(res, f)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
