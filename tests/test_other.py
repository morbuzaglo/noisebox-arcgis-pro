"""Extra tests (propy): hot reload, multi-source, drawn inputs, polygon area, DEM, receivers, compare, CRS, templates.
Usage: propy tests\\test_other.py <outdir>      (a core copy is edited in outdir, never the real one)
"""
import os
import shutil
import sys
import time

import numpy as np

from common import *  # noqa: F401,F403
from noisebox import arcgis_io as aio
from noisebox import config, pipeline
from noisebox.config import NoiseBoxError

LOG = pipeline.PrintLog()
RESULTS = []


def report(name, ok, detail=""):
    RESULTS.append(ok)
    print("RESULT %-44s %s %s" % (name, "PASS" if ok else "FAIL", detail))


def main():
    outdir = sys.argv[1]
    gdb = fresh_gdb(outdir, "other")
    base = raster(pipeline.sources_to_raster(scene(gdb, "base"), LOG)["laeq"])

    print("\n=== 1. Hot reload: edit a .m (in a COPY of matlab/core) and run again ===")
    core_copy = os.path.join(outdir, "core_copy")
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
    edited = raster(pipeline.sources_to_raster(scene(gdb, "edit"), LOG)["laeq"])
    del os.environ["NOISEBOX_CORE_DIR"]
    d = edited - base
    report("hot reload (+3 dB edit -> -3.000 dB)", abs(np.nanmin(d) + 3) < 1e-4 and abs(np.nanmax(d) + 3) < 1e-4,
           "min %.4f max %.4f" % (np.nanmin(d), np.nanmax(d)))
    again = raster(pipeline.sources_to_raster(scene(gdb, "again"), LOG)["laeq"])
    report("original code back on next run", float(np.nanmax(np.abs(again - base))) < 1e-9)

    print("\n=== 2. Two sources add by energy ===")
    s2 = os.path.join(gdb, "two_src")
    arcpy.management.CopyFeatures(os.path.join(GDB, "sources"), s2)
    with arcpy.da.InsertCursor(s2, ["SHAPE@XY", "h_src"] + ["Lw_%d" % b for b in config.BANDS]) as cur:
        cur.insertRow([(X0, Y0 + 40), 1.0] + [float(v) for v in LW])
    both = raster(pipeline.sources_to_raster(scene(gdb, "two", sources=s2, detail="Full"), LOG)["laeq"])
    sm = raster(pipeline.sources_to_raster(scene(gdb, "one", sources=os.path.join(GDB, "sources")), LOG)["laeq"])
    # second source alone = first source shifted; use energy-sum identity on an unscreened check instead:
    s_b = os.path.join(gdb, "src_b")
    arcpy.management.CopyFeatures(s2, s_b)
    arcpy.management.DeleteRows(os.path.join(s_b))  # empty copy, schema kept
    with arcpy.da.InsertCursor(s_b, ["SHAPE@XY", "h_src"] + ["Lw_%d" % b for b in config.BANDS]) as cur:
        cur.insertRow([(X0, Y0 + 40), 1.0] + [float(v) for v in LW])
    only_b = raster(pipeline.sources_to_raster(scene(gdb, "onlyb", sources=s_b), LOG)["laeq"])
    expect = 10 * np.log10(10 ** (sm / 10) + 10 ** (only_b / 10))
    report("two sources = energy sum of each alone", float(np.nanmax(np.abs(both - expect))) < 1e-3,
           "max diff %.2e dB" % np.nanmax(np.abs(both - expect)))

    print("\n=== 3. Features 'drawn on the map' (feature-set path) + defaults for NULL attributes ===")
    drawn = os.path.join(gdb, "drawn_src")
    arcpy.management.CreateFeatureclass(gdb, "drawn_src", "POINT", spatial_reference=SR)
    arcpy.management.AddField(drawn, "h_src", "DOUBLE")
    for b in config.BANDS:
        arcpy.management.AddField(drawn, "Lw_%d" % b, "DOUBLE")
    with arcpy.da.InsertCursor(drawn, ["SHAPE@XY"]) as cur:      # all attributes NULL -> defaults
        cur.insertRow([(X0, Y0)])
    r = pipeline.sources_to_raster(scene(gdb, "drawn", sources=None, sources_draw=drawn, def_h=1.0,
                                         def_lw=",".join(str(v) for v in LW)), LOG)
    dr = raster(r["laeq"])
    report("drawn source with defaults == picked source", float(np.nanmax(np.abs(dr - base))) < 1e-4)

    print("\n=== 4. Calculation area as a polygon (cells outside stay empty) ===")
    area = os.path.join(gdb, "area_tri")
    arcpy.management.CreateFeatureclass(gdb, "area_tri", "POLYGON", spatial_reference=SR)
    tri = arcpy.Polygon(arcpy.Array([arcpy.Point(X0 + 30, Y0 - 30), arcpy.Point(X0 + 130, Y0 - 30),
                                     arcpy.Point(X0 + 130, Y0 + 30)]), SR)
    with arcpy.da.InsertCursor(area, ["SHAPE@"]) as cur:
        cur.insertRow([tri])
    r = pipeline.sources_to_raster(scene(gdb, "tri", area=area, extent=None, detail="Levels only"), LOG)
    t = raster(r["laeq"])
    n_ok, n_all = int(np.isfinite(t).sum()), t.size
    same = np.nanmax(np.abs(t - base)) < 1e-4
    report("triangle area: part of the grid, values unchanged", 0 < n_ok < n_all and same, "%d of %d cells" % (n_ok, n_all))

    print("\n=== 5. DEM from the droplist raster: Israel WGS84 mosaic vs projected clip ===")
    t0 = time.time()
    a = raster(pipeline.sources_to_raster(scene(gdb, "demI", dem=DEM_ISRAEL), LOG)["laeq"])
    b = raster(pipeline.sources_to_raster(scene(gdb, "demS", dem=DEM_SAMPLE), LOG)["laeq"])
    # the two DEMs are different resamplings of the same SRTM data (30 m integer metres), so the maps differ a
    # little where the barrier shadow edge moves; the terrain effect itself (flat vs DEM) must be much larger
    mean_diff, mean_terrain = float(np.nanmean(np.abs(a - b))), float(np.nanmean(np.abs(a - base)))
    report("DEM paths agree (mean |diff| << terrain effect)", mean_diff < 1.0 and mean_diff < 0.4 * mean_terrain
           and float(np.nanmax(np.abs(a - b))) < 4.0,
           "mean |diff| %.2f dB, max %.2f dB; flat-vs-DEM mean %.2f dB (%.0f s)" % (
               mean_diff, np.nanmax(np.abs(a - b)), mean_terrain, time.time() - t0))

    print("\n=== 6. Receivers with limits and full attenuations ===")
    p = scene(gdb, "rec", receivers=os.path.join(GDB, "receivers"), receivers_draw=None, rh_field=None,
              overall=45.0, detail="Full")
    r = pipeline.points_to_fields(p, LOG)
    names = [f.name for f in arcpy.ListFields(r["receivers"])]
    need = {"LAeq", "Status", "Margin_dBA", "Lp_63", "LpA_8000", "Adiv_1000", "Aatm_8000", "Agr_500", "Abar_250",
            "DomSrc", "Dist_m", "PathType"}
    with arcpy.da.SearchCursor(r["receivers"], ["LAeq", "Status", "Margin_dBA"]) as cur:
        rows = list(cur)
    report("receiver fields present", need <= set(names) and all(x[1] in ("PASS", "FAIL") for x in rows),
           "%d fields, statuses %s" % (len(names), [x[1] for x in rows]))

    print("\n=== 7. Compare two noise maps (barrier vs none) ===")
    nob = pipeline.sources_to_raster(scene(gdb, "nobar", barriers=None), LOG)
    c = pipeline.compare_rasters({"baseline": nob["laeq"], "scenario": os.path.join(gdb, "base_LAeq"),
                                  "threshold": 3.0, "out_gdb": gdb, "run_name": "cmp", "add_map": False}, LOG)
    diff = raster(c["change"])
    report("barrier makes cells quieter", np.nanmax(diff) <= 1e-4 and np.nanmin(diff) < -3,
           "change %.1f to %.1f dB" % (np.nanmin(diff), np.nanmax(diff)))

    print("\n=== 8. Create Input Layers + templates ===")
    made = pipeline.create_input_layers({"out_gdb": gdb, "prefix": "NB_", "sr": SR, "add_map": False}, LOG)
    tmpl = aio.ensure_templates(SR)
    f1 = {f.name for f in arcpy.ListFields(made["sources"])}
    f2 = {f.name for f in arcpy.ListFields(tmpl["sources"])}
    need = {"h_src"} | {"Lw_%d" % b for b in config.BANDS}
    report("input layers/templates have the schema", need <= f1 and need <= f2 and set(made) == set(tmpl))

    print("\n=== 9. Geographic CRS is rejected ===")
    g = arcpy.management.CreateFeatureclass(gdb, "geo_s", "POINT", spatial_reference=arcpy.SpatialReference(4326))[0]
    try:
        pipeline.sources_to_raster(scene(gdb, "x", sources=g), LOG)
        report("geographic CRS rejected", False)
    except NoiseBoxError as e:
        report("geographic CRS rejected", "geographic" in str(e), str(e)[:70])

    print("\n=== 10. Timing: 40x40 cells, DEM, barrier, detail ===")
    t0 = time.time()
    pipeline.sources_to_raster(scene(gdb, "big", extent=extent(30, -100, 230, 100), cell=5.0, dem=DEM_SAMPLE,
                                     detail="Full", overall=50.0), LOG)
    print("RESULT timing: 1600 cells in %.0f s total (incl. detail cells)" % (time.time() - t0))

    print("\nALL PASS" if all(RESULTS) else "\nSOME FAILED")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
