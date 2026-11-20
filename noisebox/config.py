"""Locations and environment discovery for NoiseBox. No arcpy / MATLAB imports here.

Everything is resolved relative to the toolbox folder (the folder that holds NoiseBox.pyt),
so the whole folder can be copied to another computer and still work.
"""
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BANDS = (63, 125, 250, 500, 1000, 2000, 4000, 8000)
# Atmospheric pressure is not a tool option; ISO 9613-1 reference value.
P_KPA = 101.325


class NoiseBoxError(Exception):
    """Raised for user-facing problems (bad input, missing MATLAB / Python 3.10 ...)."""


def core_dir():
    """Folder with the MATLAB core .m files. NOISEBOX_CORE_DIR overrides it (used by tests)."""
    return os.environ.get("NOISEBOX_CORE_DIR") or os.path.join(ROOT, "matlab", "core")


def glue_dir():
    return os.path.join(ROOT, "worker", "matlab_glue")


def worker_script():
    return os.path.join(ROOT, "worker", "nb_worker.py")


def server_script():
    return os.path.join(ROOT, "worker", "nb_server.py")


def user_dir():
    """%LOCALAPPDATA%\\NoiseBox (engine state, logs). Created on demand."""
    d = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "NoiseBox")
    os.makedirs(d, exist_ok=True)
    return d


def _config_value(key, default=None):
    cfg = os.path.join(ROOT, "config.json")
    if os.path.isfile(cfg):
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                v = (json.load(f) or {}).get(key)
            if v is not None:
                return v
        except (OSError, ValueError):
            pass
    return default


ENGINE_MODES = ("warm", "fresh")


def engine_mode():
    """How MATLAB is run. "warm" (default): one MATLAB process is started on the first run and reused by the next runs
    (it reloads the .m files by itself when one of them changed); it quits after `engine_idle_minutes` without a job.
    "fresh": a new MATLAB for every run (the original behaviour: slowest start, nothing stays in memory).
    Set with the environment variable NOISEBOX_ENGINE or "engine" in <toolbox>/config.json."""
    m = (os.environ.get("NOISEBOX_ENGINE") or _config_value("engine", "warm") or "warm").strip().lower()
    return m if m in ENGINE_MODES else "warm"


def engine_idle_minutes():
    try:
        return max(1.0, float(_config_value("engine_idle_minutes", 30)))
    except (TypeError, ValueError):
        return 30.0


def find_python310():
    """Return the python.exe of the Python 3.10 environment that has the MATLAB Engine.

    Order: env var NOISEBOX_PY310, "python310" in <toolbox>/config.json,
    %LOCALAPPDATA%\\NoiseBox\\venv310\\Scripts\\python.exe.
    """
    cands = []
    if os.environ.get("NOISEBOX_PY310"):
        cands.append(("environment variable NOISEBOX_PY310", os.environ["NOISEBOX_PY310"]))
    cfg = os.path.join(ROOT, "config.json")
    if os.path.isfile(cfg):
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                p = (json.load(f) or {}).get("python310")
            if p:
                cands.append(("config.json", p))
        except (OSError, ValueError):
            pass
    local = os.environ.get("LOCALAPPDATA")
    if local:
        cands.append(("default location", os.path.join(local, "NoiseBox", "venv310", "Scripts", "python.exe")))
    for how, p in cands:
        if os.path.isfile(p):
            return p
    tried = "\n  ".join(p for _, p in cands) or "(no candidate paths)"
    raise NoiseBoxError(
        "Python 3.10 environment with the MATLAB Engine not found. Looked in:\n  " + tried +
        "\nRun setup\\setup_noisebox.ps1 (see README step 2) or set NOISEBOX_PY310 to its python.exe.")


def clean_env():
    """Environment for the Python 3.10 child process: ArcGIS Pro's PYTHON* variables would break it."""
    env = dict(os.environ)
    for k in list(env):
        if k.upper().startswith("PYTHON") or k.upper() in ("CONDA_PREFIX", "CONDA_DEFAULT_ENV", "VIRTUAL_ENV"):
            env.pop(k)
    return env


def core_hashes():
    """md5 of every .m file in the core folder (what the solver will actually run)."""
    d = core_dir()
    if not os.path.isdir(d):
        raise NoiseBoxError("MATLAB core folder not found: " + d)
    out = {}
    for name in sorted(os.listdir(d)):
        if name.lower().endswith(".m"):
            with open(os.path.join(d, name), "rb") as f:
                out[name] = hashlib.md5(f.read()).hexdigest()
    if not out:
        raise NoiseBoxError("No .m files in the MATLAB core folder: " + d)
    return out
