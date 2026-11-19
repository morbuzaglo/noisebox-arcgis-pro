"""Command line interface used by the ArcGIS Pro add-in (and usable by scripts).

    propy noisebox_cli.py <command> [arguments]

Every command prints ONE JSON document to stdout (run prints one JSON object per line: events, then a final result), so
the add-in can parse it. Exit code 0 = ran, 1 = the scenario has errors or the run failed (details are in the JSON).
"""
import argparse
import json
import os
import sys

from . import issues as I
from . import scenario as SC
from .config import NoiseBoxError


def _out(obj):
    sys.stdout.write(json.dumps(obj, default=_default) + "\n")
    sys.stdout.flush()


def _default(o):
    if isinstance(o, I.Issue):
        return o.as_dict()
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:
        pass
    return str(o)


class JsonLog:
    """Log object for the pipeline: one JSON line per event; cancel when the cancel file appears."""

    def __init__(self, cancel_file=None):
        self.cancel_file = cancel_file

    def msg(self, s):
        _out({"event": "message", "text": s})

    def warn(self, s):
        _out({"event": "warning", "text": s})

    def progress(self, d, t, s):
        _out({"event": "progress", "done": d, "total": t, "text": s})

    def cancelled(self):
        return bool(self.cancel_file and os.path.exists(self.cancel_file))


def _load(path):
    sc, iss = SC.load(path)
    if sc is None:
        _out({"ok": False, "issues": iss})
        sys.exit(1)
    return sc, iss


def main(argv=None):
    ap = argparse.ArgumentParser(prog="noisebox_cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("validate", "preview"):
        p = sub.add_parser(name)
        p.add_argument("scenario")
        p.add_argument("--fast", action="store_true", help="no GIS data access (no DTM / geodatabase checks)")
    p = sub.add_parser("run")
    p.add_argument("scenario")
    p.add_argument("--cancel-file")
    p = sub.add_parser("atmosphere")
    p.add_argument("scenario")
    p = sub.add_parser("material")
    p.add_argument("material_json", help="a face material as JSON text or a path to a .json file")
    p = sub.add_parser("parse-spectrum")
    p.add_argument("--text")
    p.add_argument("--csv")
    p = sub.add_parser("crs")
    p.add_argument("wkid", type=int)
    p = sub.add_parser("suggest-crs")
    p.add_argument("lon", type=float)
    p.add_argument("lat", type=float)
    p = sub.add_parser("dtm-info")
    p.add_argument("path")
    p = sub.add_parser("profiles")
    p.add_argument("action", choices=["list", "load", "save"])
    p.add_argument("--name")
    p.add_argument("--lw", help="8 comma separated numbers")
    p = sub.add_parser("snapshot")
    p.add_argument("gdb")
    p.add_argument("run")
    p.add_argument("--to", help="write the scenario of that run to this .json file")
    p = sub.add_parser("runs")
    p.add_argument("gdb")
    p = sub.add_parser("barrier-profile")
    p.add_argument("scenario")
    p.add_argument("barrier_id")
    p = sub.add_parser("source-from-layer")
    p.add_argument("layer")
    p.add_argument("--selected", action="store_true")
    p.add_argument("--key")
    p.add_argument("--key-field")
    p = sub.add_parser("new")
    p.add_argument("path")
    p.add_argument("--name", default="Scenario 1")
    a = ap.parse_args(argv)

    try:
        if a.cmd == "validate":
            sc, iss = _load(a.scenario)
            iss = SC.validate(sc, deep=not a.fast) + iss
            _out({"ok": not I.has_errors(iss), "counts": I.counts(iss), "issues": iss})
            return 1 if I.has_errors(iss) else 0
        if a.cmd == "preview":
            from . import scenario_run as R
            sc, _ = _load(a.scenario)
            res = R.preview(sc, deep=not a.fast)
            res["ok"] = not I.has_errors(res["issues"])
            res["counts"] = I.counts(res["issues"])
            _out(res)
            return 0 if res["ok"] else 1
        if a.cmd == "run":
            from . import scenario_run as R
            sc, _ = _load(a.scenario)
            try:
                res = R.run(sc, JsonLog(a.cancel_file))
            except R.IssuesError as e:
                _out({"event": "result", "ok": False, "issues": e.issues})
                return 1
            _out({"event": "result", "ok": True, **res})
            return 0
        if a.cmd == "atmosphere":
            from . import scenario_run as R
            sc, _ = _load(a.scenario)
            _out({"ok": True, **R.atmosphere_preview(sc)})
            return 0
        if a.cmd == "material":
            from . import scenario_run as R
            txt = a.material_json
            if os.path.isfile(txt):
                with open(txt, "r", encoding="utf-8") as f:
                    txt = f.read()
            _out({"ok": True, **R.material_preview(json.loads(txt))})
            return 0
        if a.cmd == "parse-spectrum":
            if a.csv:
                vals, iss = SC.read_spectrum_csv(a.csv)
            else:
                vals, iss = SC.parse_spectrum_text(a.text or "")
            _out({"ok": vals is not None and not I.has_errors(iss), "lw": vals, "issues": iss})
            return 0
        if a.cmd == "crs":
            _out({"ok": True, **SC.coordinate_labels(a.wkid), "wkid": a.wkid})
            return 0
        if a.cmd == "suggest-crs":
            _out({"ok": True, "wkid": SC.suggest_projected(a.lon, a.lat)})
            return 0
        if a.cmd == "dtm-info":
            info = SC.dtm_info(a.path)
            f, unit, detected = SC.dtm_unit_factor({"terrain": {"vertical_unit": None}}, info)
            info["unit_known"] = f is not None
            info["unit_text"] = unit
            _out({"ok": True, **info})
            return 0
        if a.cmd == "profiles":
            if a.action == "list":
                _out({"ok": True, "profiles": SC.list_profiles()})
            elif a.action == "load":
                _out({"ok": True, **SC.load_profile(a.name)})
            else:
                _out({"ok": True, "path": SC.save_profile(a.name, [float(v) if v else None for v in a.lw.split(",")])})
            return 0
        if a.cmd == "snapshot":
            from . import scenario_run as R
            snap = R.read_snapshot(a.gdb, a.run)
            if a.to:
                SC.save(snap["scenario"], a.to)
            _out({"ok": True, "created": snap["created"], "engine": snap["engine"], "resolved": snap["resolved"]})
            return 0
        if a.cmd == "runs":
            from . import scenario_run as R
            _out({"ok": True, "runs": R.list_runs(a.gdb)})
            return 0
        if a.cmd == "barrier-profile":
            sc, _ = _load(a.scenario)
            wkid = SC.analysis_wkid(sc)
            win = None
            if sc["terrain"].get("dtm"):
                st = next(s for s in sc["structures"] if s.get("id") == a.barrier_id)
                path = SC._barrier_path(st, wkid)
                from . import structures as S
                bb = S.bbox_of(path)
                win = SC.load_dtm_window(sc, bb, wkid, pad=50.0)
            prof, flat_top = SC.barrier_profile(sc, a.barrier_id, win)
            _out({"ok": True, "profile": [{"s": s, "ground": z, "top": t} for s, z, t in prof], "flat_top": flat_top})
            return 0
        if a.cmd == "source-from-layer":
            src, oids = SC.source_from_layer(a.layer, "selected" if a.selected else "key", a.key, a.key_field)
            _out({"ok": True, "source": src, "matching_oids": oids,
                  "issues": [I.make("SRC-009", n=len(oids), layer=src["layer"]["name"], chosen=oids[0])] if len(oids) > 1 else []})
            return 0
        if a.cmd == "new":
            sc = SC.new_scenario(a.name)
            SC.save(sc, a.path)
            _out({"ok": True, "path": a.path})
            return 0
    except NoiseBoxError as e:
        _out({"ok": False, "error": str(e)})
        return 1
    except Exception as e:      # noqa: BLE001 - the add-in must get JSON, not a traceback on stderr only
        import traceback
        _out({"ok": False, "error": "%s: %s" % (type(e).__name__, e), "trace": traceback.format_exc()})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
