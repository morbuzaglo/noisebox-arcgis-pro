"""File exchange with the Python 3.10 worker. No arcpy, no matlab imports (runs under any Python)."""
import json
import os
import shutil
import socket
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


# ---------------------------------------------------------------------------------------------- warm engine
def _state_path():
    return os.path.join(config.user_dir(), "engine.json")


def _rpc(state, req, timeout=10.0):
    """One request/response with the warm server. Raises OSError / ValueError when it is not reachable."""
    req = dict(req, token=state["token"])
    with socket.create_connection(("127.0.0.1", int(state["port"])), timeout=timeout) as s:
        s.sendall((json.dumps(req) + "\n").encode("utf-8"))
        s.settimeout(timeout)
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf.decode("utf-8"))


def _read_state():
    with open(_state_path(), "r", encoding="utf-8") as f:
        return json.load(f)


def engine_status():
    """dict(running, pid, port, jobs, started, matlab_version, idle_minutes, mode) of the warm engine."""
    try:
        r = _rpc(_read_state(), {"cmd": "ping"}, timeout=5.0)
        if r.get("ok"):
            s = r["state"]
            return {"running": True, "pid": s["pid"], "port": s["port"], "jobs": s.get("jobs", 0), "started": s.get("started"),
                    "matlab_version": s.get("matlab_version"), "idle_minutes": s.get("idle_minutes"), "mode": config.engine_mode()}
    except (OSError, ValueError, KeyError):
        pass
    return {"running": False, "mode": config.engine_mode()}


def engine_stop():
    """Ask the warm engine to quit (frees the MATLAB memory). Returns True when one was running."""
    try:
        st = _read_state()
    except (OSError, ValueError):
        return False
    try:
        _rpc(st, {"cmd": "stop"}, timeout=10.0)
        return True
    except (OSError, ValueError):
        try:
            subprocess.run(["taskkill", "/PID", str(st.get("pid")), "/T", "/F"], capture_output=True, timeout=30)
        except Exception:  # noqa: BLE001
            pass
        try:
            os.remove(_state_path())
        except OSError:
            pass
        return True


def _ensure_server(on_progress=None, is_cancelled=None, timeout=300.0):
    """Return the state of a running warm server, starting one (detached) when needed."""
    if engine_status().get("running"):
        return _read_state()
    py = config.find_python310()
    lock = os.path.join(config.user_dir(), "engine.lock")
    mine = False
    try:
        if os.path.isfile(lock) and time.time() - os.path.getmtime(lock) > timeout:
            os.remove(lock)
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        mine = True
    except OSError:
        pass  # somebody else is starting it: just wait for it
    t0 = time.time()
    try:
        if mine:
            try:
                os.remove(_state_path())
            except OSError:
                pass
            log = open(os.path.join(config.user_dir(), "engine.log"), "a", encoding="utf-8")
            # NOT DETACHED_PROCESS: tested, MATLAB's engine then needs ~19 minutes to start instead of 6 s.
            # A hidden window + own process group keeps it alive after the calling process ends; CREATE_BREAKAWAY_FROM_JOB
            # also lets it survive ArcGIS Pro's job object when that allows it.
            args = [py, "-u", config.server_script(), _state_path(), str(config.engine_idle_minutes())]
            base = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            for flags in (base | 0x01000000, base):
                try:
                    subprocess.Popen(args, cwd=config.user_dir(), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     env=config.clean_env(), close_fds=True, creationflags=flags)
                    break
                except OSError:
                    continue
        while time.time() - t0 < timeout:
            if is_cancelled and is_cancelled():
                raise NoiseBoxError("Cancelled.")
            if on_progress:
                on_progress(0, 1, "Starting MATLAB (first run only, then it stays ready) ... %d s" % int(time.time() - t0))
            if engine_status().get("running"):
                return _read_state()
            time.sleep(1.0)
    finally:
        if mine:
            try:
                os.remove(lock)
            except OSError:
                pass
    raise NoiseBoxError("The MATLAB engine did not start within %d s. See %s" % (timeout, os.path.join(config.user_dir(), "engine.log")))


def _run_warm(job_path, work, on_progress, is_cancelled):
    state = _ensure_server(on_progress, is_cancelled)
    prog_path = os.path.join(work, "progress.json")
    last = None
    with socket.create_connection(("127.0.0.1", int(state["port"])), timeout=10.0) as s:
        s.sendall((json.dumps({"cmd": "run", "job": job_path, "token": state["token"]}) + "\n").encode("utf-8"))
        s.settimeout(0.4)
        buf = b""
        while not buf.endswith(b"\n"):
            if is_cancelled and is_cancelled():
                try:
                    subprocess.run(["taskkill", "/PID", str(state["pid"]), "/T", "/F"], capture_output=True, timeout=30)
                    os.remove(_state_path())
                except Exception:  # noqa: BLE001
                    pass
                raise NoiseBoxError("Cancelled.")
            try:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
            except socket.timeout:
                pass
            if on_progress:
                try:
                    with open(prog_path, "r", encoding="utf-8") as f:
                        p = json.load(f)
                    if p != last:
                        last = p
                        on_progress(p.get("done"), p.get("total"), p.get("msg", ""))
                except (OSError, ValueError):
                    pass
    with open(os.path.join(work, "worker.log"), "w", encoding="utf-8") as f:
        f.write("warm engine pid %s\n" % state["pid"])


def run_job(job, arrays=None, on_progress=None, is_cancelled=None):
    """Write the job (+ optional float64 arrays) to a temp folder, run it in MATLAB, read result.json.

    arrays: {filename: numpy array} written as raw float64 in Fortran order (MATLAB layout).
    Returns (result_dict, work_dir). The caller reads output files from work_dir, then calls cleanup().
    The way MATLAB is run depends on config.engine_mode(): "warm" (one MATLAB kept ready between runs) or "fresh".
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
        res_path = os.path.join(work, "result.json")
        if config.engine_mode() == "warm":
            try:
                _run_warm(job_path, work, on_progress, is_cancelled)
            except (OSError, ValueError):
                # the engine process died or is unreachable: drop its state, start a new one once, and retry
                try:
                    os.remove(_state_path())
                except OSError:
                    pass
                if os.path.isfile(res_path):
                    os.remove(res_path)
                _run_warm(job_path, work, on_progress, is_cancelled)
        else:
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
        if not os.path.isfile(res_path):
            raise NoiseBoxError("The MATLAB worker ended without a result. Log tail:\n%s" % _tail(log_path))
        with open(res_path, "r", encoding="utf-8") as f:
            res = json.load(f)
        if not res.get("ok"):
            raise NoiseBoxError("MATLAB worker error: %s\n%s" % (res.get("error"), res.get("trace", "")))
        res.setdefault("engine", {"mode": "fresh"})
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
