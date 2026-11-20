"""MATLAB engine modes (propy): the warm engine must give the SAME numbers as a fresh MATLAB, reload an edited .m file on
the next run, be faster from the second run on, and stop on request.
Usage: propy tests\\test_engine.py <outdir>
"""
import os
import shutil
import sys
import time

import numpy as np

from common import *  # noqa: F401,F403
from noisebox import config, exchange, pipeline

LOG = pipeline.PrintLog()
RESULTS = []


def report(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("RESULT %-62s %s %s" % (name, "PASS" if ok else "FAIL", detail))


def timed(gdb, tag):
    t = time.time()
    out = pipeline.sources_to_raster(scene(gdb, tag), LOG)
    return raster(out["laeq"]), time.time() - t


def main():
    outdir = sys.argv[1]
    gdb = fresh_gdb(outdir, "engine")
    exchange.engine_stop()

    print("\n=== 1. fresh mode (a new MATLAB for every run) ===")
    os.environ["NOISEBOX_ENGINE"] = "fresh"
    report("engine_mode() reads NOISEBOX_ENGINE=fresh", config.engine_mode() == "fresh")
    fresh, t_fresh = timed(gdb, "fresh1")
    print("  fresh run: %.1f s" % t_fresh)
    report("fresh mode leaves no engine process behind", not exchange.engine_status()["running"])

    print("\n=== 2. warm mode ===")
    os.environ["NOISEBOX_ENGINE"] = "warm"
    report("engine_mode() reads NOISEBOX_ENGINE=warm", config.engine_mode() == "warm")
    w1, t1 = timed(gdb, "warm1")
    st = exchange.engine_status()
    report("first warm run starts the engine", st["running"], "pid %s, %.1f s" % (st.get("pid"), t1))
    w2, t2 = timed(gdb, "warm2")
    st2 = exchange.engine_status()
    print("  warm run 1: %.1f s   warm run 2: %.1f s   fresh run: %.1f s" % (t1, t2, t_fresh))
    report("same engine process reused (same pid, 2 jobs)", st2["pid"] == st["pid"] and st2["jobs"] >= 2, "jobs %s" % st2["jobs"])
    report("second warm run is faster than a fresh run", t2 < t_fresh - 3.0, "%.1f s vs %.1f s" % (t2, t_fresh))
    report("warm result == fresh result (max |difference| = 0)", float(np.nanmax(np.abs(w1 - fresh))) == 0.0 and
           float(np.nanmax(np.abs(w2 - fresh))) == 0.0, "%.2e" % float(np.nanmax(np.abs(w2 - fresh))))

    print("\n=== 3. an edited .m file is picked up by the running engine ===")
    core_copy = os.path.join(outdir, "core_copy_engine")
    shutil.rmtree(core_copy, ignore_errors=True)
    shutil.copytree(config.core_dir(), core_copy)
    f = os.path.join(core_copy, "nb_adiv.m")
    lines = open(f, "r", encoding="utf-8").read().splitlines()
    for i, l in enumerate(lines):
        if l.strip().startswith("A =") and "log10" in l:
            lines[i] = l.rstrip().rstrip(";") + " + 3;   % TEST EDIT"
            break
    else:
        raise SystemExit("could not find the Adiv expression")
    open(f, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    os.environ["NOISEBOX_CORE_DIR"] = core_copy
    edited, _ = timed(gdb, "edited")
    d = edited - fresh
    report("edit of nb_adiv.m (+3 dB in Adiv) shows as -3.000 dB, engine NOT restarted",
           abs(np.nanmin(d) + 3) < 1e-4 and abs(np.nanmax(d) + 3) < 1e-4 and exchange.engine_status()["pid"] == st["pid"],
           "min %.4f max %.4f" % (np.nanmin(d), np.nanmax(d)))
    del os.environ["NOISEBOX_CORE_DIR"]
    back, _ = timed(gdb, "back")
    report("original code is back on the next run", float(np.nanmax(np.abs(back - fresh))) == 0.0)

    print("\n=== 4. stop ===")
    stopped = exchange.engine_stop()
    time.sleep(2)
    report("engine_stop() ends the engine", stopped and not exchange.engine_status()["running"])
    again, t3 = timed(gdb, "restart")
    report("a new run after stop starts a new engine and gives the same result",
           exchange.engine_status()["running"] and float(np.nanmax(np.abs(again - fresh))) == 0.0, "%.1f s" % t3)
    exchange.engine_stop()
    print("\nRESULT: %s" % ("PASS" if all(RESULTS) else "FAIL"))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
