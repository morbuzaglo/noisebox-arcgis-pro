"""NoiseBox warm engine server. Runs in the Python 3.10 environment that has the MATLAB Engine.

Usage (started by noisebox/exchange.py, not by hand):   python nb_server.py <state.json> <idle_minutes>

Why: starting MATLAB costs 8-80 s per run. This process starts MATLAB ONCE, then serves jobs over a localhost socket
(127.0.0.1 only, random port, random token kept in <state.json>) until it has been idle for <idle_minutes>.

Hot reload is preserved: before every job the md5 of every .m file in the core folder and the glue folder is compared
with the previous job; if anything changed (or on the first job) MATLAB's function cache is cleared and the path is
refreshed, so an edited .m file takes effect on the very next run, exactly as with a fresh MATLAB. The result of a job
is written to <work_dir>/result.json in the same format as nb_worker.py, plus an "engine" block (mode, reused,
reloaded, start time) so it is always visible which way a result was computed.

The Python side never imports matlab.engine; only this process (and nb_worker.py) does.
"""
import json
import os
import secrets
import socket
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from nb_worker import md5_dir  # noqa: E402


def glue_result(job, py_hashes):
    rp = os.path.join(job["work_dir"], "glue_result.json")
    out = {}
    if os.path.isfile(rp):
        with open(rp, "r", encoding="utf-8") as f:
            out["glue"] = json.load(f)
        fp = out["glue"].get("fingerprint")
        if fp:
            ml = dict(zip(fp["file"], fp["md5"]))
            out["fingerprint_match"] = (ml == py_hashes)
    return out


def main():
    state_path = sys.argv[1]
    idle_s = float(sys.argv[2]) * 60.0
    t0 = time.time()
    import matlab.engine  # only in the Python 3.10 environment

    eng = matlab.engine.start_matlab()
    start_s = round(time.time() - t0, 1)
    matlab_version = eng.version(nargout=1)

    token = secrets.token_hex(16)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    srv.settimeout(2.0)
    port = srv.getsockname()[1]
    state = {"pid": os.getpid(), "port": port, "token": token, "started": time.time(), "start_s": start_s,
             "matlab_version": matlab_version, "python": sys.version.split()[0], "idle_minutes": idle_s / 60.0, "jobs": 0}

    def write_state():
        tmp = state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, state_path)

    write_state()
    last_hashes = None
    last_activity = time.time()
    try:
        while True:
            if time.time() - last_activity > idle_s:
                break
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            with conn:
                conn.settimeout(30.0)
                try:
                    req = json.loads(conn.makefile("r", encoding="utf-8").readline())
                except Exception:  # noqa: BLE001
                    continue
                if req.get("token") != token:
                    conn.sendall(b'{"ok": false, "error": "bad token"}\n')
                    continue
                last_activity = time.time()
                cmd = req.get("cmd")
                if cmd == "ping":
                    conn.sendall((json.dumps({"ok": True, "state": state}) + "\n").encode())
                    continue
                if cmd == "stop":
                    conn.sendall(b'{"ok": true}\n')
                    break
                if cmd != "run":
                    conn.sendall(b'{"ok": false, "error": "unknown command"}\n')
                    continue
                conn.settimeout(None)
                with open(req["job"], "r", encoding="utf-8") as f:
                    job = json.load(f)
                out = os.path.join(job["work_dir"], "result.json")
                t1 = time.time()
                try:
                    hashes = {}
                    hashes.update({"core/" + k: v for k, v in md5_dir(job["core_dir"]).items()})
                    hashes.update({"glue/" + k: v for k, v in md5_dir(job["glue_dir"]).items()})
                    reloaded = hashes != last_hashes
                    if reloaded:
                        eng.eval("clear functions; clear all; rehash;", nargout=0)
                        last_hashes = hashes
                    eng.addpath(job["core_dir"], job["glue_dir"], nargout=0)
                    if reloaded:
                        eng.rehash(nargout=0)
                    eng.nb_job(os.path.join(job["work_dir"], "job.json"), nargout=0)
                    res = {"ok": True, "python": sys.version.split()[0], "matlab_version": matlab_version,
                           "engine_start_s": start_s if state["jobs"] == 0 else 0.0, "total_s": round(time.time() - t1, 1),
                           "core_dir": job["core_dir"], "core_md5": md5_dir(job["core_dir"]),
                           "engine": {"mode": "warm", "reused": state["jobs"] > 0, "reloaded_m_files": reloaded,
                                      "server_pid": os.getpid()}}
                    res.update(glue_result(job, res["core_md5"]))
                except BaseException as e:  # noqa: BLE001 (report everything to the caller)
                    res = {"ok": False, "error": "%s: %s" % (type(e).__name__, e), "trace": traceback.format_exc()}
                    last_hashes = None  # force a clean reload after an error
                with open(out, "w", encoding="utf-8") as f:
                    json.dump(res, f)
                state["jobs"] += 1
                write_state()
                last_activity = time.time()
                try:
                    conn.sendall(b'{"ok": true}\n')
                except OSError:
                    pass
    finally:
        try:
            eng.quit()
        except Exception:  # noqa: BLE001
            pass
        try:
            os.remove(state_path)
        except OSError:
            pass


if __name__ == "__main__":
    main()
