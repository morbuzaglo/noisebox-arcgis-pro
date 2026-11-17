"""Shared helpers for the propy tests."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import arcpy  # noqa: E402

GDB = os.path.join(ROOT, "sample", "NoiseBox_sample.gdb")
DEM_SAMPLE = os.path.join(ROOT, "sample", "dem_sample.tif")
DEM_ISRAEL = os.path.join(ROOT, "data", "dem", "Israel_SRTM_30m.tif")
X0, Y0 = 180000.0, 665000.0
SR = arcpy.SpatialReference(2039)
LW = [100, 100, 100, 100, 100, 95, 90, 85]
arcpy.env.overwriteOutput = True


def fresh_gdb(outdir, name):
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, name + ".gdb")
    if arcpy.Exists(path):
        arcpy.management.Delete(path)
    arcpy.management.CreateFileGDB(outdir, name)
    return path


def extent(x1=30, y1=-30, x2=130, y2=30):
    e = arcpy.Extent(X0 + x1, Y0 + y1, X0 + x2, Y0 + y2)
    e.spatialReference = SR
    return e


def scene(out_gdb, run="t", **kw):
    """Parameter dict for pipeline.sources_to_raster: sample source + barrier, flat, 100 x 60 m at 10 m."""
    p = {"sources": os.path.join(GDB, "sources"), "sources_draw": None, "h_field": "h_src", "lw_prefix": "Lw_",
         "barriers": os.path.join(GDB, "barrier"), "barriers_draw": None, "b_field": "h_bar", "dem": None,
         "G": 0.5, "hr": 1.5, "T": 15.0, "RH": 70.0, "mode": "iso2024",
         "area": None, "area_draw": None, "extent": extent(), "clip": True, "cell": 10.0,
         "overall": None, "weighting": "Z", "band_limits": [None] * 8,
         "out_gdb": out_gdb, "run_name": run, "iso_step": 0, "bands": False, "detail": "None",
         "copy_inputs": False, "add_map": False}
    p.update(kw)
    return p


def raster(path):
    import numpy as np
    r = arcpy.Raster(path)
    try:
        return arcpy.RasterToNumPyArray(r, nodata_to_value=np.nan).astype("float64")
    except ValueError:                       # integer rasters (e.g. pass/fail): NoData -> NaN by hand
        a = arcpy.RasterToNumPyArray(r, nodata_to_value=-9999).astype("float64")
        a[a == -9999] = np.nan
        return a
