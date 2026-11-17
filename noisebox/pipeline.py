"""High-level tool logic, shared by NoiseBox.pyt and the standalone tests (propy).

`log` is any object with: msg(str), warn(str), progress(done, total, text), cancelled() -> bool.
"""
import math
import os

import numpy as np

from . import arcgis_io as aio
from . import config, exchange
from . import outputs as out
from .config import BANDS, NoiseBoxError

MAX_CELLS_SOURCES = 2_000_000    # hard stop: cells x sources
MAX_DETAIL_CELLS = 100_000       # above this no per-cell detail polygons are written
SECONDS_PER_CELL_SOURCE = 0.007  # measured: 1600 cells, 1 source, barrier + DEM took ~11 s after engine start
DEFAULT_LW = "100,100,100,100,100,95,90,85"


class PrintLog:
    def msg(self, s): print(s)
    def warn(self, s): print("WARNING:", s)
    def progress(self, d, t, s): print("  [%s/%s] %s" % (d, t, s))
    def cancelled(self): return False


# ---------------------------------------------------------------- shared
def _settings(p):
    G = float(p["G"])
    if not 0.0 <= G <= 1.0:
        raise NoiseBoxError("Ground factor G must be between 0 and 1.")
    if float(p["hr"]) <= 0:
        raise NoiseBoxError("Receiver height must be > 0.")
    if not 0 < float(p["RH"]) <= 100:
        raise NoiseBoxError("Relative humidity must be 0-100 %.")
    if p["mode"] not in ("iso2024", "draft2026", "iso1996"):
        raise NoiseBoxError("Unknown formula mode: %s" % p["mode"])
    detail = p.get("detail") or "Full"
    if detail not in ("Full", "Levels only", "None"):
        raise NoiseBoxError("Detail must be Full, Levels only or None.")
    lim = exchange.limits_job(p.get("overall"), p.get("band_limits"), p.get("weighting") or "Z")
    return {"G": G, "hr": float(p["hr"]), "T_C": float(p["T"]), "RH": float(p["RH"]), "mode": p["mode"],
            "limits": lim, "detail": detail, "want_bands": bool(p.get("bands")) or detail != "None"}


def _bbox(points_xy, extent=None):
    xs = [x for x, _ in points_xy]
    ys = [y for _, y in points_xy]
    if extent is not None:
        xs += [extent[0], extent[2]]
        ys += [extent[1], extent[3]]
    return (min(xs), min(ys), max(xs), max(ys))


def _inputs(p, log):
    """Resolve sources (picked or drawn) and barriers. -> (sr, sources, source_fc, barrier_fc, barrier_field, default_bh)."""
    arcpy = aio._arcpy()
    src_fc = aio.pick(p.get("sources"), p.get("sources_draw"))
    if not src_fc:
        raise NoiseBoxError("No sources: pick a source layer in section 1, or draw source points on the map.")
    drawn = bool(p.get("sources_draw")) and src_fc == p.get("sources_draw")
    sr = arcpy.Describe(src_fc).spatialReference
    aio.require_metric_projected(sr, "The source layer")
    if drawn:
        defaults = (float(p.get("def_h") or 1.0), aio.parse_lw(p.get("def_lw") or DEFAULT_LW))
        sources = aio.read_sources(src_fc, sr, "h_src", "Lw_", defaults)
        log.msg("Sources drawn on the map: %d (empty height / Lw fields use the defaults)." % len(sources))
    else:
        sources = aio.read_sources(src_fc, sr, p["h_field"], p["lw_prefix"] or "Lw_")
        log.msg("Sources from layer: %d." % len(sources))
    bar_fc = aio.pick(p.get("barriers"), p.get("barriers_draw"))
    bar_drawn = bool(p.get("barriers_draw")) and bar_fc == p.get("barriers_draw")
    bar_field = "h_bar" if bar_drawn else p.get("b_field")
    if bar_fc and not bar_field:
        raise NoiseBoxError("Choose the barrier height field.")
    def_bh = float(p.get("def_bh") or 4.0) if bar_drawn else None
    return sr, sources, src_fc, bar_fc, bar_field, def_bh


def _area(p, sr, sources, log):
    """-> (bbox, rings or None, area_fc or None)."""
    fc = aio.pick(p.get("area"), p.get("area_draw"))
    if fc:
        bbox, rings = aio.read_area(fc, sr)
        log.msg("Calculation area: polygon (%d ring(s)); cells outside it are left empty." % len(rings))
        return bbox, (rings if p.get("clip", True) else None), fc
    ext = p.get("extent")
    if ext is not None:
        if ext.spatialReference is not None and ext.spatialReference.factoryCode and \
                ext.spatialReference.factoryCode != sr.factoryCode:
            ext = ext.projectAs(sr)
        log.msg("Calculation area: rectangle from the extent.")
        return (ext.XMin, ext.YMin, ext.XMax, ext.YMax), None, None
    pad = 300.0
    b = _bbox([(s["x"], s["y"]) for s in sources])
    log.msg("No calculation area given: using the sources' bounding box + %d m." % pad)
    return (b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad), None, None


def _scene(p, sr, bbox, bar_fc, bar_field, def_bh, log):
    pad = max(100.0, 0.05 * max(bbox[2] - bbox[0], bbox[3] - bbox[1]))
    obstacles = aio.read_obstacles(bar_fc, sr, bar_field, bbox, def_bh) if bar_fc else []
    log.msg("Barriers/buildings used: %d" % len(obstacles))
    if p.get("dem"):
        dem, Z, nod = aio.dem_from_raster(p["dem"], sr, bbox, pad)
        log.msg("DEM: %d x %d cells of %.1f m (resampled to the analysis CRS)" % (dem["nx"], dem["ny"], dem["cs"]))
        if nod > 0:
            log.warn("%.1f %% of the DEM window is NoData; receivers there become NoData." % (100 * nod))
    else:
        dem, Z = aio.flat_dem(bbox, pad)
        log.msg("No DEM given: flat ground at elevation 0.")
    return obstacles, dem, Z


def _report_code(res, log):
    log.msg("MATLAB %s, Python %s; engine start %.1f s, total %.1f s" %
            (res.get("matlab_version"), res.get("python"), res.get("engine_start_s", 0), res.get("total_s", 0)))
    if res.get("fingerprint_match") is False:
        log.warn("The .m file hashes seen by MATLAB differ from those on disk.")
    h = config.core_hashes()
    log.msg("Core .m files: %d (md5 of nb_adiv.m: %s)" % (len(h), h.get("nb_adiv.m", "?")[:12]))


def _need_gdb(p):
    gdb = p.get("out_gdb")
    arcpy = aio._arcpy()
    if not gdb:
        raise NoiseBoxError("Choose an output geodatabase (section 6).")
    if not arcpy.Exists(gdb):
        raise NoiseBoxError("The output geodatabase does not exist: %s" % gdb)
    return gdb


def _status_of(code):
    return np.array([out.STATUS.get(int(c), "NO DATA") if np.isfinite(c) else "NO DATA" for c in code])


# ---------------------------------------------------------------- noise map
def sources_to_raster(p, log):
    """Noise map. Returns dict of created items {role: path}."""
    arcpy = aio._arcpy()
    gdb = _need_gdb(p)
    sr, sources, src_fc, bar_fc, bar_field, def_bh = _inputs(p, log)
    settings = _settings(p)
    bbox, rings, area_fc = _area(p, sr, sources, log)
    cs = p.get("cell")
    if not cs:
        cs = aio.auto_cell(bbox)
        log.msg("Cell size not given: using %g m (about 150 cells across)." % cs)
    cs = float(cs)
    grid, ll = aio.make_grid(bbox, cs)
    nx, ny = grid["nx"], grid["ny"]
    ncell = nx * ny
    xc = grid["x0"] + np.arange(nx) * cs
    yc = grid["y0"] + np.arange(ny) * cs
    if rings:
        XX, YY = np.meshgrid(xc, yc)
        inside = aio.points_in_rings(XX.ravel(), YY.ravel(), rings).reshape(ny, nx)
        if not inside.any():
            raise NoiseBoxError("No cell centre lies inside the calculation-area polygon. Use a smaller cell size.")
    else:
        inside = np.ones((ny, nx), dtype=bool)
    active_rows = [int(i) + 1 for i in np.flatnonzero(inside.any(axis=1))]
    n_active = int(inside.sum())
    log.msg("Grid %d x %d = %d cells of %g m (%d inside the area); %d source(s)." %
            (nx, ny, ncell, cs, n_active, len(sources)))
    if ncell * len(sources) > MAX_CELLS_SOURCES:
        raise NoiseBoxError("%d cells x %d sources is too many for this tool (limit %d). Use a larger cell size "
                            "or a smaller area." % (ncell, len(sources), MAX_CELLS_SOURCES))
    if settings["detail"] != "None" and n_active > MAX_DETAIL_CELLS:
        log.warn("%d cells is above %d: the clickable detail cells are skipped. Use a larger cell size for them."
                 % (n_active, MAX_DETAIL_CELLS))
        settings["detail"] = "None"
        settings["want_bands"] = bool(p.get("bands")) or settings["limits"] is not None
    est_min = len(active_rows) * nx * len(sources) * SECONDS_PER_CELL_SOURCE / 60.0 + 0.3
    log.msg("Estimated run time: about %.1f min (MATLAB start-up ~10-80 s, then ~%d ms per cell and source)."
            % (est_min, int(SECONDS_PER_CELL_SOURCE * 1000)))
    if est_min > 20:
        log.warn("This will take a while. A larger cell size or a smaller area runs much faster.")
    scene_bbox = _bbox([(s["x"], s["y"]) for s in sources], bbox)
    obstacles, dem, Z = _scene(p, sr, scene_bbox, bar_fc, bar_field, def_bh, log)
    job = exchange.build_job(settings, sources, obstacles, dem, grid=grid)
    job["chunk_rows"] = max(1, 1500 // nx)
    job["active_rows"] = active_rows

    run = out.unique_run_name(gdb, p.get("run_name") or "NoiseRun")
    res, work = exchange.run_job(job, {"dem.bin": Z}, on_progress=log.progress, is_cancelled=log.cancelled)
    try:
        _report_code(res, log)
        arr = exchange.read_arrays(work, res, ncell)
    finally:
        exchange.cleanup(work)
    closure = (res.get("glue") or {}).get("closure_max_abs_dB")
    if closure is not None and len(sources) == 1 and settings["detail"] == "Full":
        log.msg("Detail check: Lp = Lw - (Adiv+Aatm+Agr+Abar) holds to %.2e dB." % closure)

    flat_inside = inside.ravel()
    for k in list(arr):                                   # cells outside the polygon -> NoData
        a = arr[k]
        a[~flat_inside] = np.nan
    laeq = arr["LAeq"].reshape(ny, nx)
    valid = np.isfinite(laeq)
    n_ok = int(valid.sum())
    log.msg("Valid cells: %d of %d inside the area (NaN = inside a barrier, at a source, or outside the DEM)"
            % (n_ok, n_active))
    if n_ok == 0:
        raise NoiseBoxError("No valid cells were computed. Check that the area lies inside the DEM and outside "
                            "the barrier polygons.")
    lim = settings["limits"]
    has_lim = lim is not None
    overall = lim["overall"] if has_lim and lim["has_overall"] else None

    # ---- write
    created = {}
    names = {}
    names["laeq"] = out.out_path(gdb, run + "_LAeq")
    out.write_raster(laeq, ll, cs, sr, names["laeq"])
    created["laeq"] = names["laeq"]
    log.msg("LAeq range: %.1f to %.1f dB(A)" % (np.nanmin(laeq), np.nanmax(laeq)))
    if p.get("bands"):
        for i, b in enumerate(BANDS):
            path = out.out_path(gdb, "%s_Lp%d" % (run, b))
            out.write_raster(arr["Lp"][:, i].reshape(ny, nx), ll, cs, sr, path)
            created["Lp%d" % b] = path
    step = float(p.get("iso_step") or 0)
    if step > 0:
        path = out.out_path(gdb, run + "_Bands")
        out.write_isophones(laeq, ll, cs, sr, step, path)
        created["bands"] = path
    if has_lim:
        margin = arr["margin_overall"] if overall is not None else arr["worst_margin"]
        path = out.out_path(gdb, run + "_Margin")
        out.write_raster(margin.reshape(ny, nx), ll, cs, sr, path)
        created["margin"] = path
        path = out.out_path(gdb, run + "_PassFail")
        out.write_passfail(arr["code"].reshape(ny, nx), ll, cs, sr, path)
        created["passfail"] = path
    if settings["detail"] != "None":
        dom = arr.get("dom")
        if dom is not None:
            ids_src = np.array([s["id"] for s in sources], dtype="float64")
            arr["dom_id"] = np.where(np.isfinite(dom), ids_src[np.clip(np.nan_to_num(dom, nan=1).astype(int) - 1, 0,
                                                                          len(sources) - 1)], np.nan)
        ids = np.arange(1, ncell + 1, dtype="int32")
        v = np.isfinite(arr["LAeq"])
        sub = {k: a[v] for k, a in arr.items()}
        struct = out.cell_arrays(sub, int(v.sum()), ids[v], has_lim, has_lim and bool(np.any(lim["bands_set"])))
        ids2d = np.where(v.reshape(ny, nx), ids.reshape(ny, nx), 0)
        path = out.out_path(gdb, run + "_Cells")
        out.write_cells(ids2d, struct, ll, cs, sr, path)
        created["cells"] = path
    # inputs used (a copy, so the run can be reproduced even if the originals change)
    if p.get("copy_inputs", True):
        for role, fc, nm in (("in_sources", src_fc, "_Sources"), ("in_barriers", bar_fc, "_Barriers"),
                             ("in_area", area_fc, "_Area")):
            if fc:
                path = out.out_path(gdb, run + nm)
                arcpy.management.CopyFeatures(fc, path)
                created[role] = path

    # ---- summary table
    rows = [("Mode", None, "", settings["mode"]), ("Cells calculated", n_ok, "cells", ""),
            ("Cell size", cs, "m", ""), ("Sources", len(sources), "", ""),
            ("Barriers/buildings", len(obstacles), "", ""), ("LAeq minimum", float(np.nanmin(laeq)), "dB(A)", ""),
            ("LAeq maximum", float(np.nanmax(laeq)), "dB(A)", ""),
            ("LAeq mean (arithmetic over cells)", float(np.nanmean(laeq)), "dB(A)", ""),
            ("Ground factor G", settings["G"], "", ""), ("Temperature", settings["T_C"], "deg C", ""),
            ("Relative humidity", settings["RH"], "%", ""), ("Receiver height", settings["hr"], "m", "")]
    if has_lim:
        code = arr["code"]
        nfail = int((code == 0).sum())
        npass = int((code == 1).sum())
        tot = max(nfail + npass, 1)
        rows += [("Overall limit", overall, "dB(A)", "none" if overall is None else ""),
                 ("Area above a limit", nfail * cs * cs, "m2", "cells where any limit is exceeded"),
                 ("Share of area above a limit", 100.0 * nfail / tot, "%", ""),
                 ("Largest exceedance", float(np.nanmax(np.where(code == 0, (arr["margin_overall"] if overall is not None
                                                                           else arr["worst_margin"]), np.nan)))
                  if nfail else 0.0, "dB", "")]
        log.msg("Limit check: %d cells PASS, %d FAIL (%.1f %% of the area above a limit)." %
                (npass, nfail, 100.0 * nfail / tot))
    summ = out.out_path(gdb, run + "_Summary")
    out.write_summary(rows, summ)
    created["summary"] = summ
    log.msg("Summary table: " + summ)

    # ---- map
    sink = out.MapSink(bool(p.get("add_map", True)), log)
    if sink.on:
        _add_noise_map_to_map(sink, run, created, settings, has_lim, overall, p, log)
    return created


def _add_noise_map_to_map(sink, run, c, settings, has_lim, overall, p, log):
    top = sink.group("NoiseBox: " + run)
    g_in = sink.group(run + " | 4 Inputs", top, visible=False)
    g_ins = sink.group(run + " | 3 Inspect", top) if "cells" in c else None
    g_lim = sink.group(run + " | 2 Limit check", top) if has_lim else None
    g_res = sink.group(run + " | 1 Results", top)
    if "in_area" in c:
        sink.add(c["in_area"], g_in, run + " area", style=out.style_area)
    if "in_barriers" in c:
        sink.add(c["in_barriers"], g_in, run + " barriers", style=out.style_barriers)
    if "in_sources" in c:
        sink.add(c["in_sources"], g_in, run + " sources")
    if "cells" in c:
        sink.add(c["cells"], g_ins, "Detail cells: click a cell to read all values", style=out.style_invisible_cells)
    if has_lim:
        if "margin" in c:
            sink.add(c["margin"], g_lim, "Margin to limit (dB, + = exceeds)", visible=False, style=out.style_margin)
        sink.add(c["passfail"], g_lim, "Limit check (PASS / FAIL)", style=out.style_passfail)
    if p.get("bands"):
        g_b = sink.group(run + " | Octave bands (Lp, unweighted)", g_res, visible=False)
        for b in reversed(BANDS):
            sink.add(c["Lp%d" % b], g_b, "Lp %d Hz (dB)" % b, visible=False, style=out.style_level)
    if "bands" in c:
        sink.add(c["bands"], g_res, "Noise bands dB(A)", visible=False, style=out.style_bands)
    sink.add(c["laeq"], g_res, "LAeq dB(A)", style=out.style_level)


# ---------------------------------------------------------------- receivers
def points_to_fields(p, log):
    arcpy = aio._arcpy()
    gdb = _need_gdb(p)
    sr, sources, src_fc, bar_fc, bar_field, def_bh = _inputs(p, log)
    rec_fc = aio.pick(p.get("receivers"), p.get("receivers_draw"))
    if not rec_fc:
        raise NoiseBoxError("No receivers: pick a point layer in section 4, or draw points on the map.")
    rdesc = arcpy.Describe(rec_fc)
    if rdesc.shapeType != "Point":
        raise NoiseBoxError("Receivers must be a point feature class.")
    aio.require_metric_projected(rdesc.spatialReference, "The receiver layer")
    settings = _settings(p)
    settings["detail"] = "Full" if settings["detail"] != "None" else "None"
    run = out.unique_run_name(gdb, p.get("run_name") or "Receivers")
    path_out = out.out_path(gdb, run + "_Receivers")
    arcpy.management.CopyFeatures(rec_fc, path_out)
    drawn = bool(p.get("receivers_draw")) and rec_fc == p.get("receivers_draw")
    hname = "h_rec" if drawn else p.get("rh_field")
    hf = aio.find_field(path_out, hname, "Receiver height") if hname else None
    receivers, oids = [], []
    flds = ["OID@", "SHAPE@XY"] + ([hf] if hf else [])
    with arcpy.da.SearchCursor(path_out, flds, spatial_reference=sr) as cur:
        for row in cur:
            h = row[2] if hf else None
            if h is None:
                h = settings["hr"]
            if row[1] is None or row[1][0] is None:
                continue
            if not math.isfinite(h) or h <= 0:
                raise NoiseBoxError("Receiver OID %s: height must be > 0." % row[0])
            oids.append(row[0])
            receivers.append({"x": float(row[1][0]), "y": float(row[1][1]), "h": float(h)})
    if not receivers:
        raise NoiseBoxError("The receiver layer has no features.")
    bbox = _bbox([(s["x"], s["y"]) for s in sources] + [(r["x"], r["y"]) for r in receivers])
    obstacles, dem, Z = _scene(p, sr, bbox, bar_fc, bar_field, def_bh, log)
    job = exchange.build_job(settings, sources, obstacles, dem, receivers=receivers)
    n = len(receivers)
    res, work = exchange.run_job(job, {"dem.bin": Z}, on_progress=log.progress, is_cancelled=log.cancelled)
    try:
        _report_code(res, log)
        arr = exchange.read_arrays(work, res, n)
    finally:
        exchange.cleanup(work)
    ids_src = np.array([s["id"] for s in sources], dtype="float64")
    arr["dom_id"] = np.where(np.isfinite(arr["dom"]),
                             ids_src[np.clip(np.nan_to_num(arr["dom"], nan=1).astype(int) - 1, 0, len(sources) - 1)],
                             np.nan)
    lim = settings["limits"]
    has_lim = lim is not None
    full = settings["detail"] == "Full"
    sub = dict(arr)
    if not full:
        for k in ("Adiv", "Aatm", "Agr", "Abar"):
            sub.pop(k, None)
    struct = out.cell_arrays(sub, n, np.array(oids, dtype="int32"), has_lim, has_lim and bool(np.any(lim["bands_set"])))
    existing = {f.name.lower() for f in arcpy.ListFields(path_out)}
    names = [x for x in struct.dtype.names if x != "Cell_ID"]
    for nm in names:
        if nm.lower() in existing:
            raise NoiseBoxError("The receiver layer already has a field named %s; rename it first." % nm)
        if struct.dtype[nm].kind == "U":
            arcpy.management.AddField(path_out, nm, "TEXT", field_length=24)
        else:
            arcpy.management.AddField(path_out, nm, "DOUBLE")
    lut = {int(o): i for i, o in enumerate(oids)}
    nbad = 0
    with arcpy.da.UpdateCursor(path_out, ["OID@"] + names) as cur:
        for row in cur:
            i = lut.get(row[0])
            if i is None:
                continue
            vals = []
            for nm in names:
                v = struct[nm][i]
                if struct.dtype[nm].kind == "U":
                    vals.append(str(v))
                else:
                    vals.append(None if not math.isfinite(v) else float(v))
            if struct["LAeq"][i] is None or not math.isfinite(struct["LAeq"][i]):
                nbad += 1
            cur.updateRow([row[0]] + vals)
    log.msg("Wrote %d fields (LAeq, per-band Lp/LpA%s) to %s" %
            (len(names), ", attenuations Adiv/Aatm/Agr/Abar" if full else "", path_out))
    if has_lim:
        st = _status_of(arr["code"])
        log.msg("Limit check at receivers: %d PASS, %d FAIL." % (int((st == "PASS").sum()), int((st == "FAIL").sum())))
    if nbad:
        log.warn("%d receiver(s) are NULL (inside a barrier, at a source, or outside the DEM)." % nbad)
    sink = out.MapSink(bool(p.get("add_map", True)), log)
    if sink.on:
        top = sink.group("NoiseBox: " + run)
        sink.add(path_out, top, run + " receivers (click for levels)")
    return {"receivers": path_out}


# ---------------------------------------------------------------- compare
def compare_rasters(p, log):
    """Scenario minus baseline (dB). Same grid required."""
    arcpy = aio._arcpy()
    gdb = _need_gdb(p)
    a, b = p.get("baseline"), p.get("scenario")
    if not a or not b:
        raise NoiseBoxError("Pick a baseline raster and a scenario raster.")
    ra, rb = arcpy.Raster(a), arcpy.Raster(b)
    ea, eb = ra.extent, rb.extent
    if (abs(ra.meanCellWidth - rb.meanCellWidth) > 1e-6 or abs(ea.XMin - eb.XMin) > 1e-3 or abs(ea.YMin - eb.YMin) > 1e-3
            or ra.width != rb.width or ra.height != rb.height):
        raise NoiseBoxError("The two rasters are not on the same grid (extent / cell size). Run both noise maps "
                            "with the same calculation area and cell size.")
    A = arcpy.RasterToNumPyArray(ra, nodata_to_value=np.nan).astype("float64")
    B = arcpy.RasterToNumPyArray(rb, nodata_to_value=np.nan).astype("float64")
    D = B - A
    ok = np.isfinite(D)
    if not ok.any():
        raise NoiseBoxError("The rasters have no overlapping valid cells.")
    run = out.unique_run_name(gdb, p.get("run_name") or "Compare")
    path = out.out_path(gdb, run + "_Change")
    ll = (ea.XMin, ea.YMin)
    out.write_raster(np.flipud(D), ll, ra.meanCellWidth, ra.spatialReference, path)
    cs = ra.meanCellWidth
    thr = float(p.get("threshold") or 3.0)
    quieter = int((D <= -thr).sum())
    louder = int((D >= thr).sum())
    n = int(ok.sum())
    log.msg("Change (scenario - baseline): min %.1f, max %.1f, mean %.2f dB over %d cells." %
            (np.nanmin(D), np.nanmax(D), np.nanmean(D), n))
    log.msg("Quieter by >= %g dB: %.1f %% of cells (%d m2); louder by >= %g dB: %.1f %% (%d m2)." %
            (thr, 100.0 * quieter / n, quieter * cs * cs, thr, 100.0 * louder / n, louder * cs * cs))
    sink = out.MapSink(bool(p.get("add_map", True)), log)
    if sink.on:
        top = sink.group("NoiseBox: " + run)
        sink.add(path, top, "Change in dB(A) (negative = quieter)", style=out.style_diff)
    return {"change": path}


# ---------------------------------------------------------------- inputs template
def create_input_layers(p, log):
    arcpy = aio._arcpy()
    gdb = _need_gdb(p)
    sr = p.get("sr") or aio.default_template_sr()
    aio.require_metric_projected(sr, "The chosen coordinate system")
    made = aio.create_layers(gdb, p.get("prefix") or "NB_", sr)
    for k, v in made.items():
        log.msg("Created %s: %s" % (k, v))
    sink = out.MapSink(bool(p.get("add_map", True)), log)
    if sink.on:
        top = sink.group("NoiseBox inputs: " + (p.get("prefix") or "NB_"))
        sink.add(made["area"], top, "Calculation area", style=out.style_area)
        sink.add(made["receivers"], top, "Receivers")
        sink.add(made["barriers"], top, "Barriers / buildings", style=out.style_barriers)
        sink.add(made["sources"], top, "Sources")
    log.msg("Draw features with the Create Features pane. Sources need h_src and Lw_63 ... Lw_8000 "
            "(dB re 1 pW, unweighted).")
    return made


# ---------------------------------------------------------------- link check
def check_link(log):
    ok = True
    log.msg("Toolbox folder: %s" % config.ROOT)
    py = config.find_python310()
    log.msg("Python 3.10 environment: %s" % py)
    h = config.core_hashes()
    log.msg("Core folder: %s (%d .m files)" % (config.core_dir(), len(h)))
    res, work = exchange.run_job({"action": "check", "mode": "iso2024"}, {}, on_progress=None,
                                 is_cancelled=log.cancelled)
    try:
        log.msg("Python in worker: %s" % res.get("python"))
        log.msg("MATLAB Engine OK, MATLAB %s (engine start %.1f s)" % (res.get("matlab_version"),
                                                                        res.get("engine_start_s", 0)))
        if res.get("fingerprint_match"):
            log.msg(".m hashes: MATLAB nb_fingerprint == files on disk (%d files)." % len(h))
        else:
            log.warn(".m hashes differ between MATLAB and disk!")
            ok = False
        sm = (res.get("glue") or {}).get("smoke") or {}
        log.msg("Solver smoke test (%s): LpA = %.2f dB(A), Lp = %.2f dB" %
                (sm.get("case"), sm.get("LpA_broadband", float("nan")), sm.get("Lp_broadband", float("nan"))))
    finally:
        exchange.cleanup(work)
    return ok
