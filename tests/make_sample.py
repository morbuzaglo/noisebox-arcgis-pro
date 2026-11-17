"""Build the sample dataset (sample/NoiseBox_sample.gdb + sample/dem_sample.tif).  Run with propy.

Synthetic scene in Israeli TM Grid (EPSG 2039), Tel Aviv area:
  * 1 point source  (h = 1.0 m, Lw 100 dB in 63-1000 Hz falling to 85 dB at 8 kHz)
  * 1 barrier       (200 m x 0.5 m wall, 4 m high) 20 m east of the source
  * 4 receiver points behind the barrier / beside it
  * a 1 km DEM clip from data/dem/Israel_SRTM_30m.tif (optional; only if that file exists)
"""
import os
import sys

import arcpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "sample")
GDB = os.path.join(SAMPLE, "NoiseBox_sample.gdb")
SR = arcpy.SpatialReference(2039)
X0, Y0 = 180000.0, 665000.0          # source position
BANDS = (63, 125, 250, 500, 1000, 2000, 4000, 8000)
LW = (100, 100, 100, 100, 100, 95, 90, 85)


def main():
    os.makedirs(SAMPLE, exist_ok=True)
    if arcpy.Exists(GDB):
        print("Sample gdb exists, leaving it:", GDB)
        make_dem()
        return
    arcpy.management.CreateFileGDB(SAMPLE, "NoiseBox_sample")

    src = arcpy.management.CreateFeatureclass(GDB, "sources", "POINT", spatial_reference=SR)[0]
    arcpy.management.AddField(src, "h_src", "DOUBLE")
    for b, _ in zip(BANDS, LW):
        arcpy.management.AddField(src, "Lw_%d" % b, "DOUBLE")
    with arcpy.da.InsertCursor(src, ["SHAPE@XY", "h_src"] + ["Lw_%d" % b for b in BANDS]) as c:
        c.insertRow([(X0, Y0), 1.0] + [float(v) for v in LW])

    bar = arcpy.management.CreateFeatureclass(GDB, "barrier", "POLYGON", spatial_reference=SR)[0]
    arcpy.management.AddField(bar, "h_bar", "DOUBLE")
    pts = [(X0 + 20.0, Y0 - 100.0), (X0 + 20.0, Y0 + 100.0), (X0 + 20.5, Y0 + 100.0), (X0 + 20.5, Y0 - 100.0)]
    poly = arcpy.Polygon(arcpy.Array([arcpy.Point(*p) for p in pts]), SR)
    with arcpy.da.InsertCursor(bar, ["SHAPE@", "h_bar"]) as c:
        c.insertRow([poly, 4.0])

    rec = arcpy.management.CreateFeatureclass(GDB, "receivers", "POINT", spatial_reference=SR)[0]
    with arcpy.da.InsertCursor(rec, ["SHAPE@XY"]) as c:
        for dx, dy in ((40, 0), (60, 10), (100, -20), (30, 5)):
            c.insertRow([(X0 + dx, Y0 + dy)])
    print("Created", GDB)
    make_dem()


def make_dem():
    israel = os.path.join(ROOT, "data", "dem", "Israel_SRTM_30m.tif")
    out = os.path.join(SAMPLE, "dem_sample.tif")
    if os.path.isfile(israel) and not os.path.isfile(out):
        # clip a small window in the source's own (geographic) CRS first, then project: keeps the sample tiny
        win = arcpy.Extent(X0 - 500, Y0 - 500, X0 + 500, Y0 + 500)
        win.spatialReference = SR
        g = win.projectAs(arcpy.SpatialReference(4326))
        tmp = "memory/dem_win"
        arcpy.management.Clip(israel, "%f %f %f %f" % (g.XMin - 0.002, g.YMin - 0.002, g.XMax + 0.002, g.YMax + 0.002),
                              tmp, maintain_clipping_extent="NO_MAINTAIN_EXTENT")
        arcpy.management.ProjectRaster(tmp, out, SR, "BILINEAR", "30 30")
        arcpy.management.Delete(tmp)
        print("Created", out)


if __name__ == "__main__":
    main()
