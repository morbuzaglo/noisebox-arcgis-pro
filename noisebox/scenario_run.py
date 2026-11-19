"""Preview and run a scenario. Builds the job from the scenario, runs the MATLAB core through the worker, writes outputs.

No acoustic formula lives here (same rule as the rest of the project): the numbers come from matlab/core via
worker/matlab_glue/nb_job.m. Needs arcpy (propy) for GIS data and outputs.
"""
import json
import os
from datetime import datetime

import numpy as np

from . import arcgis_io as aio
from . import config, exchange, issues as I, scenario as SC, structures as S
from . import outputs as out
from .config import BANDS, NoiseBoxError
from .pipeline import PrintLog


class IssuesError(NoiseBoxError):
    """The scenario cannot run; .issues holds every Issue found."""

    def __init__(self, issues):
        self.issues = issues
        errs = [i for i in issues if i.severity == I.ERROR]
        super().__init__("%d error(s) stop the run:\n" % len(errs) + "\n".join("  " + str(i) for i in errs[:12]))


# ------------------------------------------------------------------ resolved scene (shared by preview and run)
def resolve_scene(sc):
    """Everything the run needs, in the analysis CRS. Assumes validate() found no errors."""
    wkid = SC.analysis_wkid(sc)
    sxy = SC.source_xy(sc, wkid)
    rings, bbox = SC.area_rings(sc, wkid)
    info = SC.dtm_info(sc["terrain"]["dtm"]["path"]) if sc["terrain"].get("dtm") else None
    cs = SC.cell_size(sc, info)
    factor = SC.dtm_unit_factor(sc, info)[0] if info else 1.0
    inc = [s for s in sc["structures"] if s.get("include", True)]
    return {"wkid": wkid, "sxy": sxy, "rings": rings, "bbox": bbox, "info": info, "cs": cs, "factor": factor or 1.0,
            "included": inc}


def source_job(sc, scene):
    """The point source for the core: position, height above local ground, Lw, Dc and the enclosure (if included)."""
    s = sc["source"]
    d = s["directivity"]
    dc = [0.0] * 8 if d.get("mode") == "omni" else [float(v) for v in d["dc"]]
    enc = None
    for st in scene["included"]:
        if st["type"] == "enclosure":
            enc, _, _ = SC.enclosure_job(st, scene["sxy"], scene["wkid"])
    return {"x": scene["sxy"][0], "y": scene["sxy"][1], "h": float(s["height_m"]),
            "Lw": [float(v) for v in s["spectrum"]["lw"]], "Dc": dc, "enclosure": enc}


def obstacles_job(sc, scene):
    """Included buildings and barriers as engine obstacles (all keys present in every entry)."""
    obs, bld_rings = [], []
    wkid = scene["wkid"]
    for st in scene["included"]:
        if st["type"] == "building":
            ring = S.clean_ring(SC._xf_ring(st, "footprint", wkid))
            bld_rings.append((np.array([p[0] for p in ring]), np.array([p[1] for p in ring])))
            obs.append(S.building_obstacle(ring, st["height_m"]))
        elif st["type"] == "barrier":
            path = SC._barrier_path(st, wkid)
            obs += S.barrier_obstacles(path, st["vertical"], SC.barrier_material_job(st), st.get("gap_m") or None)
    return obs, bld_rings


# ------------------------------------------------------------------ preview (no MATLAB)
def preview(sc, deep=True):
    """Fast checks and everything needed to draw the scenario. No acoustic calculation."""
    iss = SC.validate(sc, deep=deep)
    res = {"issues": iss, "scenario": sc["name"]}
    wkid = SC.analysis_wkid(sc)
    info = None
    if deep and sc["terrain"].get("dtm") and not any(i.code in ("DTM-002", "DTM-003", "DTM-004") for i in iss):
        try:
            info = SC.dtm_info(sc["terrain"]["dtm"]["path"])
        except Exception:
            info = None
    res["dtm"] = info
    res["summaries"] = SC.section_summaries(sc)
    res["effects"] = SC.active_effects(sc)
    errs_before_geometry = any(i.severity == I.ERROR and i.section in ("source", "area", "scenario") for i in iss)
    if wkid and not errs_before_geometry:
        sxy = SC.source_xy(sc, wkid)
        rings, bbox = SC.area_rings(sc, wkid)
        res["source"] = {"x": sxy[0], "y": sxy[1], "wkid": wkid, "height_m": sc["source"]["height_m"],
                         "heading_deg": sc["source"]["directivity"].get("heading_deg", 0.0),
                         "heading_vec": S.azimuth_vec(sc["source"]["directivity"].get("heading_deg", 0.0)),
                         "origin": sc["source"].get("origin")}
        res["area"] = {"rings": rings, "bbox": bbox}
        res["grid"] = SC.estimate(sc, info)
        if deep and sc["terrain"].get("dtm") and info is not None:
            more, cov, win = SC.deep_dtm_checks(sc, wkid)
            res["issues"] = I.sort_issues(res["issues"] + more)
            res["coverage"] = cov
            res["elevation"] = None
            if cov and cov["source_ground"] is not None:
                h = sc["source"]["height_m"] or 0.0
                res["elevation"] = {"ground_m": cov["source_ground"], "height_m": h,
                                    "absolute_m": cov["source_ground"] + h}
    res["structures"] = []
    sxy_ok = res.get("source") and (res["source"]["x"], res["source"]["y"])
    for st in sc["structures"]:
        item = {"id": st.get("id"), "name": st.get("name"), "type": st.get("type"),
                "include": st.get("include", True), "visible": st.get("visible", True),
                "state": ("in the run" if st.get("include", True) else "excluded from the run") + ", " +
                         ("drawn" if st.get("visible", True) else "hidden on the map")}
        if st.get("type") == "enclosure" and sxy_ok and wkid:
            try:
                ring = SC.enclosure_ring(st, sxy_ok, wkid)
                if ring and st.get("height_m"):
                    faces = S.enclosure_faces(ring, st["height_m"])
                    item["faces"] = [{"name": f["name"], "area": f["area"], "p1": f["p1"], "p2": f["p2"],
                                      "data": _face_data_state(SC.face_material(st, f["name"]))} for f in faces]
                    item["ring"] = ring
            except Exception:                      # incomplete input: the issues list already says what is missing
                pass
        if st.get("type") == "barrier" and wkid:
            p = SC._barrier_path(st, wkid)
            if p:
                item["path"] = p
                item["length_m"] = S.path_length(p)
        res["structures"].append(item)
    return res


def _face_data_state(fm):
    """'measured' | 'estimated' | 'missing' for the material preview table."""
    if not fm:
        return "missing"
    if fm.get("mode") == "manufacturer":
        return "measured" if fm.get("TL") and all(v is not None for v in fm["TL"]) else "missing"
    return "estimated" if SC._mass_of(fm) is not None else "missing"


def list_runs(gdb):
    """Runs with a snapshot in a geodatabase: [{run, created, name}]."""
    arcpy = aio._arcpy()
    prev = arcpy.env.workspace
    arcpy.env.workspace = gdb
    try:
        tabs = [t for t in (arcpy.ListTables("*_Snapshot") or [])]
    finally:
        arcpy.env.workspace = prev
    out_ = []
    for t in tabs:
        run = t[: -len("_Snapshot")]
        try:
            snap = read_snapshot(gdb, run)
            out_.append({"run": run, "created": snap["created"], "name": snap["scenario"]["name"]})
        except Exception:
            continue
    return sorted(out_, key=lambda r: r["created"], reverse=True)


# ------------------------------------------------------------------ run
def _scale_style(vmin, vmax, unit):
    def style(lyr, aprx):
        sym = lyr.symbology
        sym.updateColorizer("RasterClassifyColorizer")
        col = sym.colorizer
        n = max(2, int(round((vmax - vmin) / 5.0)))
        col.classificationField = "Value"
        col.breakCount = n
        ramp = out._ramp(aprx, "Orange-Red (Continuous)", "Yellow-Orange-Red")
        if ramp:
            col.colorRamp = ramp
        step = (vmax - vmin) / n
        for i, cb in enumerate(col.classBreaks):
            lo, hi = vmin + i * step, vmin + (i + 1) * step
            cb.upperBound = hi
            cb.label = "%g to %g %s" % (lo, hi, unit)
        lyr.symbology = sym
    return style


def _level_style(shared, unit):
    if shared:
        fixed = _scale_style(shared["min"], shared["max"], unit)

        def style(lyr, aprx):
            try:
                fixed(lyr, aprx)
            except Exception:
                out.style_level(lyr, aprx)
        return style
    return out.style_level


def run(sc, log=None):
    """Validate, calculate and write. Returns a dict: created datasets, statistics, issues, snapshot table."""
    log = log or PrintLog()
    arcpy = aio._arcpy()
    iss = SC.validate(sc, deep=True)
    scene = None
    if not I.has_errors(iss):
        scene = resolve_scene(sc)
        more, cov, win = SC.deep_dtm_checks(sc, scene["wkid"])
        iss = I.sort_issues(iss + more)
    for i in iss:
        if i.severity == I.WARNING:
            log.warn(str(i))
        elif i.severity == I.INFO:
            log.msg(str(i))
    if I.has_errors(iss):
        raise IssuesError(iss)

    o = sc["outputs"]
    gdb = o["gdb"]
    wkid, sxy, rings, bbox, cs = scene["wkid"], scene["sxy"], scene["rings"], scene["bbox"], scene["cs"]
    sr = arcpy.SpatialReference(wkid)
    grid, ll = aio.make_grid(bbox, cs)
    nx, ny = grid["nx"], grid["ny"]
    ncell = nx * ny
    xc = grid["x0"] + np.arange(nx) * cs
    yc = grid["y0"] + np.arange(ny) * cs
    XX, YY = np.meshgrid(xc, yc)
    ring_arrays = [(np.array([p[0] for p in r]), np.array([p[1] for p in r])) for r in rings]
    inside = aio.points_in_rings(XX.ravel(), YY.ravel(), ring_arrays).reshape(ny, nx)
    if not inside.any():
        raise IssuesError([I.make("ARA-025", cell=cs)])
    active_rows = [int(i) + 1 for i in np.flatnonzero(inside.any(axis=1))]
    n_active = int(inside.sum())
    log.msg("Receiver grid %d x %d = %d cells of %g m (%d inside the area)." % (nx, ny, ncell, cs, n_active))

    source = source_job(sc, scene)
    obstacles, bld_rings = obstacles_job(sc, scene)
    detail_full = o.get("detail") == "Full" and n_active <= SC.MAX_DETAIL_CELLS
    if o.get("detail") == "Full" and not detail_full:
        log.warn(I.make("ARA-020", cells=n_active, limit=SC.MAX_DETAIL_CELLS).message)
    has_lim = o.get("limit_dba") is not None
    want_bands = bool(o.get("overall_z") or o.get("bands") or has_lim or detail_full)

    # ---- terrain
    scene_pts = [sxy] + [p for r in rings for p in r]
    for ob in obstacles:
        scene_pts += list(zip(ob["x"], ob["y"]))
    sbb = S.bbox_of(scene_pts)
    pad = max(100.0, 0.05 * max(sbb[2] - sbb[0], sbb[3] - sbb[1]))
    if sc["terrain"].get("dtm"):
        dem, Z, nod = aio.dem_from_raster(sc["terrain"]["dtm"]["path"], sr, sbb, pad)
        Z = Z * scene["factor"]
        log.msg("DTM %s: %d x %d cells of %.1f m (%.1f %% NoData in the window)." %
                (sc["terrain"]["dtm"].get("name", ""), dem["nx"], dem["ny"], dem["cs"], 100 * nod))
    else:
        dem, Z = aio.flat_dem(sbb, pad)
        log.msg("No DTM: flat ground at elevation 0 m.")

    p = sc["propagation"]
    g = p["ground"]
    settings = {"G": g["Gm"] if g.get("separate") else g["G"], "hr": float(sc["area"]["receiver_height_m"]),
                "T_C": float(p["atmosphere"]["T_C"]), "RH": float(p["atmosphere"]["RH"]), "mode": p["mode"],
                "limits": exchange.limits_job(o.get("limit_dba"), None, "Z"),
                "detail": "Full" if detail_full else "Levels only", "want_bands": want_bands}
    job = exchange.build_job(settings, [source], obstacles, dem, grid=grid)
    job["atm"]["p_kPa"] = float(p["atmosphere"]["p_kPa"])
    if g.get("separate"):
        job["Gadv"] = {"Gs": float(g["Gs"]), "Gm": float(g["Gm"]), "Gr": float(g["Gr"])}
    if p["meteorology"].get("method") == "long_term":
        job["C0"] = float(p["meteorology"]["C0"])
    job["chunk_rows"] = max(1, 1500 // nx)
    job["active_rows"] = active_rows

    est = n_active * SC.SECONDS_PER_CELL_SOURCE / 60.0 + 0.3
    log.msg("Estimated run time about %.1f min (MATLAB start-up 10-80 s, then about 7 ms per cell)." % est)
    run_name = out.unique_run_name(gdb, o["run_name"])
    if run_name != o["run_name"]:
        log.msg(I.make("OUT-007", name=o["run_name"], unique=run_name).message)

    res, work = exchange.run_job(job, {"dem.bin": Z}, on_progress=log.progress, is_cancelled=log.cancelled)
    try:
        arr = exchange.read_arrays(work, res, ncell)
    finally:
        exchange.cleanup(work)
    glue = res.get("glue") or {}
    if res.get("fingerprint_match") is False:
        log.warn(I.make("ENG-004").message)
    flat_inside = inside.ravel()
    for k in list(arr):
        arr[k][~flat_inside] = np.nan
    laeq = arr["LAeq"].reshape(ny, nx)
    n_ok = int(np.isfinite(laeq).sum())
    if n_ok == 0:
        raise IssuesError([I.make("ENG-007")])
    pct_empty = 100.0 * (n_active - n_ok) / n_active
    if pct_empty > 0.5:
        log.warn(I.make("ENG-008", pct=pct_empty).message)
    n_in_bld = 0
    if bld_rings:
        n_in_bld = int((aio.points_in_rings(XX.ravel(), YY.ravel(), bld_rings) & flat_inside).sum())
        log.msg(I.make("BLD-013", n=n_in_bld).message)
    for r in glue.get("enclosures") or []:
        if r:
            bad = [b for b, v in zip(BANDS, r["notApplicableBands"]) if v]
            if bad:
                log.warn(I.make("ENG-014", bands=", ".join(map(str, bad)), name=sc["source"].get("name")).message)
            log.msg("Enclosure: radiated Lw reduced by %.1f to %.1f dB (mean %.1f dB) across the bands." %
                    (min(r["reduction"]), max(r["reduction"]), float(np.mean(r["reduction"]))))

    # ---- outputs
    created = {}
    mode_txt = p["mode"]
    shared = o.get("shared_scale")
    if not (shared and SC._finite(shared.get("min")) and SC._finite(shared.get("max"))):
        shared = None                                   # both empty = no shared scale (invalid pairs were rejected earlier)
    lmin, lmax = float(np.nanmin(laeq)), float(np.nanmax(laeq))
    if shared and (lmin < shared["min"] or lmax > shared["max"]):
        log.warn(I.make("OUT-013", lmin=lmin, lmax=lmax, vmin=shared["min"], vmax=shared["max"]).message)
    if o.get("overall_a"):
        created["laeq"] = out.write_raster(laeq, ll, cs, sr, out.out_path(gdb, run_name + "_LAeq"))
    if o.get("overall_z"):
        created["lz"] = out.write_raster(arr["LZ"].reshape(ny, nx), ll, cs, sr, out.out_path(gdb, run_name + "_LZ"))
    for b in o.get("bands") or []:
        i = BANDS.index(b)
        created["Lp%d" % b] = out.write_raster(arr["Lp"][:, i].reshape(ny, nx), ll, cs, sr,
                                               out.out_path(gdb, "%s_Lp%d" % (run_name, b)))
    if has_lim:
        created["margin"] = out.write_raster(arr["margin_overall"].reshape(ny, nx), ll, cs, sr,
                                             out.out_path(gdb, run_name + "_Margin"))
        pth = out.out_path(gdb, run_name + "_PassFail")
        out.write_passfail(arr["code"].reshape(ny, nx), ll, cs, sr, pth)
        created["passfail"] = pth
    if detail_full:
        dom = arr["dom"]
        arr["dom_id"] = np.where(np.isfinite(dom), 1.0, np.nan)
        ids = np.arange(1, ncell + 1, dtype="int32")
        v = np.isfinite(arr["LAeq"])
        sub = {k: a[v] for k, a in arr.items()}
        struct = out.cell_arrays(sub, int(v.sum()), ids[v], has_lim, False)
        ids2d = np.where(v.reshape(ny, nx), ids.reshape(ny, nx), 0)
        pth = out.out_path(gdb, run_name + "_Cells")
        out.write_cells(ids2d, struct, ll, cs, sr, pth)
        created["cells"] = pth

    rows = [("Scenario", None, "", sc["name"][:119]), ("Prediction mode", None, "", SC.MODES[mode_txt][:119]),
            ("Cells calculated", n_ok, "cells", ""), ("Cell size", cs, "m", ""),
            ("Receiver height above local ground", settings["hr"], "m", ""),
            ("Cells inside building footprints", n_in_bld, "cells", "left empty (NoData)"),
            ("LAeq minimum", lmin, "dB(A)", ""), ("LAeq maximum", lmax, "dB(A)", ""),
            ("Source height above ground", source["h"], "m", "")]
    rows += [("Active effect %d" % (i + 1), None, "", e[:119]) for i, e in enumerate(SC.active_effects(sc))]
    if has_lim:
        code = arr["code"]
        nfail, npass = int((code == 0).sum()), int((code == 1).sum())
        rows += [("Limit", o["limit_dba"], "dB(A)", ""), ("Area above the limit", nfail * cs * cs, "m2", ""),
                 ("Share of area above the limit", 100.0 * nfail / max(nfail + npass, 1), "%", "")]
    created["summary"] = out.out_path(gdb, run_name + "_Summary")
    out.write_summary(rows, created["summary"])

    # ---- snapshot: scenario + what was resolved + which code ran, so the run can be reproduced later
    snap = {"scenario": sc, "run_name": run_name, "created": datetime.now().isoformat(timespec="seconds"),
            "resolved": {"analysis_wkid": wkid, "source_xy": list(sxy), "cell_m": cs, "grid": [nx, ny],
                         "enclosure_Lw_effective": (np.atleast_2d(glue["Lw_effective"]).tolist()
                                                    if glue.get("Lw_effective") is not None else None),
                         "n_obstacles": len(obstacles),
                         "included_structures": [s["name"] for s in scene["included"]]},
            "engine": {"matlab": res.get("matlab_version"), "core_md5": res.get("core_md5"),
                       "fingerprint_match": res.get("fingerprint_match")}}
    created["snapshot"] = write_snapshot(gdb, run_name, snap)

    sink = out.MapSink(bool(o.get("add_to_map", True)), log)
    if sink.on:
        _add_to_map(sink, sc, run_name, created, shared, mode_txt)
    log.msg("Done: %s" % run_name)
    return {"run_name": run_name, "created": created, "issues": iss,
            "stats": {"cells": n_ok, "laeq_min": lmin, "laeq_max": lmax, "cells_in_buildings": n_in_bld},
            "engine": snap["engine"]}


def _add_to_map(sink, sc, run, c, shared, mode):
    top = sink.group("NoiseBox: %s | %s" % (sc["name"], run))
    qual = " [%s]" % mode
    unit = "dB"
    lvl = _level_style(shared, unit)
    if "cells" in c:
        g = sink.group(run + " | Inspect", top)
        sink.add(c["cells"], g, "Detail cells: click a cell to read all values", style=out.style_invisible_cells)
    if "passfail" in c:
        g = sink.group(run + " | Limit check", top)
        if "margin" in c:
            sink.add(c["margin"], g, "Margin to limit (dB, + = exceeds)", visible=False, style=out.style_margin)
        sink.add(c["passfail"], g, "Limit check (PASS / FAIL)", style=out.style_passfail)
    band_keys = [k for k in c if k.startswith("Lp")]
    if band_keys:
        g = sink.group(run + " | Octave bands (Lp, unweighted)", top, visible=False)
        for b in reversed(BANDS):
            if "Lp%d" % b in c:
                sink.add(c["Lp%d" % b], g, "Lp %d Hz, dB" % b + qual, visible=False, style=lvl)
    if "lz" in c:
        sink.add(c["lz"], top, "Lz unweighted energy sum of 8 bands, dB" + qual, visible=False, style=lvl)
    if "laeq" in c:
        sink.add(c["laeq"], top, "LAeq, dB(A)" + qual, style=lvl)


# ------------------------------------------------------------------ snapshots
def write_snapshot(gdb, run, snap):
    arcpy = aio._arcpy()
    path = out.out_path(gdb, run + "_Snapshot")
    arcpy.management.CreateTable(gdb, os.path.basename(path))
    arcpy.management.AddField(path, "RUN", "TEXT", field_length=100)
    arcpy.management.AddField(path, "CREATED", "TEXT", field_length=30)
    arcpy.management.AddField(path, "SCENARIO", "TEXT", field_length=8_000_000)
    with arcpy.da.InsertCursor(path, ["RUN", "CREATED", "SCENARIO"]) as cur:
        cur.insertRow([run, snap["created"], json.dumps(snap)])
    return path


def read_snapshot(gdb, run):
    arcpy = aio._arcpy()
    path = out.out_path(gdb, run + "_Snapshot")
    with arcpy.da.SearchCursor(path, ["SCENARIO"]) as cur:
        for (txt,) in cur:
            return json.loads(txt)
    raise NoiseBoxError("No snapshot in %s." % path)


# ------------------------------------------------------------------ previews that need the core
def material_preview(face_material):
    """TL per octave band as the core resolves it (mass law or measured). Starts MATLAB (10-80 s)."""
    job = {"action": "material", "mat": SC._mat_job(face_material), "mode": "iso2024", "hr": 1.5, "G": 0.5,
           "atm": {"T_C": 15, "RH": 70, "p_kPa": 101.325}}
    res, work = exchange.run_job(job)
    exchange.cleanup(work)
    return res["glue"]


def atmosphere_preview(sc):
    """Atmospheric absorption coefficient alpha (dB/km) per band for the scenario's T, RH, p and mode (the core)."""
    a = sc["propagation"]["atmosphere"]
    job = {"action": "atmosphere", "mode": sc["propagation"]["mode"], "hr": 1.5, "G": 0.5,
           "atm": {"T_C": float(a["T_C"]), "RH": float(a["RH"]), "p_kPa": float(a["p_kPa"])}}
    res, work = exchange.run_job(job)
    exchange.cleanup(work)
    return res["glue"]
