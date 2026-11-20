"""Runs every test in order and writes docs/test_summary.json (used by the manual). Usage: propy tests\\run_all.py <outdir>
The MATLAB tests take about 30-40 minutes in total (each run starts MATLAB)."""
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
out = sys.argv[1]
os.makedirs(out, exist_ok=True)
TESTS = [
    ("Scenario validation, geometry, spectrum input, source methods (260-entry catalogue)", "test_scenario.py", True, False),
    ("Command line used by the add-in (JSON, DTM coverage)", "test_cli.py", True, False),
    ("Add-in package: DAML vs Esri schema, classNames, refIDs, zip layout", "check_addin_package.py", False, False),
    ("Add-in pane: XAML bindings, handlers, converters, focus targets", "check_xaml_bindings.py", False, False),
    ("Original toolbox vs the MATLAB core (raster, bands, every detail field)", "test_synthetic.py", True, True),
    ("Original toolbox: hot reload, 2 sources, drawn inputs, polygon area, DEM, receivers, compare", "test_other.py", True, True),
    ("Scenario runs on the MATLAB core: baseline, barrier, enclosure, Dc, C0, G, outputs, previews, snapshot", "test_scenario_engine.py", True, True),
    ("MATLAB engine modes: warm engine == fresh MATLAB, hot reload of an edited .m, faster from the 2nd run", "test_engine.py", True, True),
    ("Allowed levels: overall dB(A) and per-band limits, one exceeded limit = FAIL", "test_limits.py", True, True),
    ("All toolbox tools through ArcPy's geoprocessing framework (incl. Run Scenario)", "test_pyt.py", True, True),
]
lines = []
for title, script, wants_out, _matlab in TESTS:
    t0 = time.time()
    cmd = [sys.executable, "-u", os.path.join(HERE, script)] + ([os.path.join(out, script[:-3])] if wants_out else [])
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
    txt = p.stdout + p.stderr
    open(os.path.join(out, script + ".log"), "w", encoding="utf-8").write(txt)
    ok = len(re.findall(r"RESULT .* PASS", txt)) + len(re.findall(r"^RESULT: PASS", txt, flags=re.M))
    bad = len(re.findall(r"RESULT .* FAIL", txt))
    verdict = "PASS" if p.returncode == 0 and bad == 0 else "FAIL"
    lines.append([title, "%s: %d checks passed, %d failed, exit code %d (%.0f s)" % (verdict, ok, bad, p.returncode, time.time() - t0)])
    json.dump({"lines": lines, "finished": False}, open(os.path.join(ROOT, "docs", "test_summary.json"), "w", encoding="utf-8"), indent=1)
    print(script, verdict, ok, bad, flush=True)
json.dump({"lines": lines, "finished": True}, open(os.path.join(ROOT, "docs", "test_summary.json"), "w", encoding="utf-8"), indent=1)
print("DONE", flush=True)
