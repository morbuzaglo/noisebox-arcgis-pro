"""File exchange with the Python 3.10 worker. No arcpy, no matlab imports (runs under any Python)."""
import json
import os
import shutil
import subprocess
import tempfile
import time

import numpy as np

from . import config
from .config import NoiseBoxError


def _kill_tree(proc):
    try:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=30)
    except Exception:
        proc.kill()


def _tail(path, n=25):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-n:])
    except OSError:
        return ""


def run_job(job, arrays=None, on_progress=None, is_cancelled=None):
    """Write the job (+ optional float64 arrays) to a temp folder, run the worker, read result.json.

    arrays: {filename: numpy array} written as raw float64 in Fortran order (MATLAB layout).
    Returns (result_dict, work_dir). The caller reads output files from work_dir, then calls cleanup().
    """
    py = config.find_python310()
    work = tempfile.mkdtemp(prefix="noisebox_")
    try:
        for name, arr in (arrays or {}).items():
            with open(os.path.join(work, name), "wb") as f:
                f.write(np.asarray(arr, dtype="<f8").tobytes(order="F"))
        job = dict(job)
        job["work_dir"] = work
        job["core_dir"] = config.core_dir()
        job["glue_dir"] = config.glue_dir()
        job_path = os.path.join(work, "job.json")
        with open(job_path, "w", encoding="utf-8") as f:
            json.dump(job, f)
        log_path = os.path.join(work, "worker.log")
        with open(log_path, "w", encoding="utf-8") as log:
            proc = subprocess.Popen(
                [py, "-u", config.worker_script(), job_path], cwd=work, stdout=log, stderr=subprocess.STDOUT,
                env=config.clean_env(),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            prog_path = os.path.join(work, "progress.json")
            last = None
            while proc.poll() is None:
                time.sleep(0.4)
                if is_cancelled and is_cancelled():
                    _kill_tree(proc)
                    raise NoiseBoxError("Cancelled.")
                if on_progress:
                    try:
                        with open(prog_path, "r", encoding="utf-8") as f:
                            p = json.load(f)
                        if p != last:
                            last = p
                            on_progress(p.get("done"), p.get("total"), p.get("msg", ""))
                    except (OSError, ValueError):
                        pass
        res_path = os.path.join(work, "result.json")
        if not os.path.isfile(res_path):
            raise NoiseBoxError("The MATLAB worker ended without a result (exit code %s). Log tail:\n%s"
                                % (proc.returncode, _tail(log_path)))
        with open(res_path, "r", encoding="utf-8") as f:
            res = json.load(f)
        if not res.get("ok"):
            raise NoiseBoxError("MATLAB worker error: %s\n%s" % (res.get("error"), res.get("trace", "")))
        return res, work
    except BaseException:
        cleanup(work)
        raise


def cleanup(work):
    if os.environ.get("NOISEBOX_KEEP_TEMP"):
        return
    shutil.rmtree(work, ignore_errors=True)


def read_f8(work, name, shape):
    """Read a raw float64 file written by MATLAB fwrite (column-major)."""
    a = np.fromfile(os.path.join(work, name), dtype="<f8")
    return a.reshape(shape, order="F")


def read_arrays(work, res, n):
    """Arrays listed in the glue manifest -> {name: (n,) or (n, k) float64}."""
    out = {}
    for name, k in ((res.get("glue") or {}).get("arrays") or {}).items():
        a = read_f8(work, "out_%s.bin" % name, (n, int(k)))
        out[name] = a[:, 0] if int(k) == 1 else a
    return out


def limits_job(overall=None, band_limits=None, weighting="Z"):
    """Limits dict for the job, or None when no limit is set. band_limits: 8 numbers / None."""
    bl = list(band_limits or [None] * 8)
    bl = [None if (v is None or v == "") else float(v) for v in bl]
    if overall in ("", None) and not any(v is not None for v in bl):
        return None
    return {"bands_set": [v is not None for v in bl], "bands": [0.0 if v is None else v for v in bl],
            "weighting": weighting if weighting in ("Z", "A") else "Z",
            "has_overall": overall not in ("", None), "overall": 0.0 if overall in ("", None) else float(overall)}


def build_job(settings, sources, obstacles, dem, grid=None, receivers=None):
    """Assemble the job dict. `dem` = dict(x0, y0, cs, nx, ny) (Z goes to dem.bin separately)."""
    job = {
        "mode": settings["mode"],
        "hr": settings["hr"],
        "G": settings["G"],
        "atm": {"T_C": settings["T_C"], "RH": settings["RH"], "p_kPa": config.P_KPA},
        "dem": dem,
        "sources": [{k: v for k, v in s.items() if k != "id"} for s in sources],
        "obstacles": obstacles,
        "limits": settings.get("limits"),
        "detail": "full" if settings.get("detail") == "Full" else "none",
        "want_bands": bool(settings.get("want_bands")),
    }
    if grid is not None:
        job["action"] = "field"
        job["grid"] = grid
    else:
        job["action"] = "points"
        job["receivers"] = receivers
    return job
