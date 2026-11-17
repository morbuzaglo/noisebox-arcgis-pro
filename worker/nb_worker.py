"""NoiseBox worker. Runs in the Python 3.10 environment that has the MATLAB Engine.

Usage:  python nb_worker.py <job.json>
Reads the job, starts MATLAB, runs worker/matlab_glue/nb_job.m (which calls the core .m files),
and writes <work_dir>/result.json. The ArcGIS-side code never imports matlab.engine.

Hot reload: every run is a fresh process, so MATLAB always loads the current .m files. As a belt-and-braces
step the worker also clears MATLAB's function cache and refreshes the path before the run, and it reports the
md5 of every core .m file (Python-side and MATLAB-side nb_fingerprint) so a result can be tied to the code.
"""
import hashlib
import json
import os
import sys
import time
import traceback


def md5_dir(d):
    out = {}
    for n in sorted(os.listdir(d)):
        if n.lower().endswith(".m"):
            with open(os.path.join(d, n), "rb") as f:
                out[n] = hashlib.md5(f.read()).hexdigest()
    return out


def run(job):
    import matlab.engine  # only available in the Python 3.10 environment

    t0 = time.time()
    core, glue = job["core_dir"], job["glue_dir"]
    py_hashes = md5_dir(core)
    eng = matlab.engine.start_matlab()
    try:
        t_start = time.time() - t0
        eng.eval("clear functions; clear all; rehash;", nargout=0)
        eng.addpath(core, glue, nargout=0)
        eng.rehash(nargout=0)
        eng.nb_job(os.path.join(job["work_dir"], "job.json"), nargout=0)
        matlab_version = eng.version(nargout=1)
    finally:
        try:
            eng.quit()
        except Exception:
            pass
    res = {"ok": True, "python": sys.version.split()[0], "matlab_version": matlab_version,
           "engine_start_s": round(t_start, 1), "total_s": round(time.time() - t0, 1),
           "core_dir": core, "core_md5": py_hashes}
    rp = os.path.join(job["work_dir"], "glue_result.json")
    if os.path.isfile(rp):
        with open(rp, "r", encoding="utf-8") as f:
            res["glue"] = json.load(f)
        # the md5 MATLAB computed (nb_fingerprint) must equal ours: proves one code path
        fp = res["glue"].get("fingerprint")
        if fp:
            ml = dict(zip(fp["file"], fp["md5"]))
            res["fingerprint_match"] = (ml == py_hashes)
    return res


def main():
    job_path = sys.argv[1]
    with open(job_path, "r", encoding="utf-8") as f:
        job = json.load(f)
    out = os.path.join(job["work_dir"], "result.json")
    try:
        res = run(job)
    except BaseException as e:  # noqa: BLE001  (report everything to the caller)
        res = {"ok": False, "error": "%s: %s" % (type(e).__name__, e), "trace": traceback.format_exc()}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f)


if __name__ == "__main__":
    main()
