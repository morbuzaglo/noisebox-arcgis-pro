"""Download SRTM 1-arc-second tiles covering Israel and mosaic them into data/dem/Israel_SRTM_30m.tif.

Run with ArcGIS Pro's Python:  propy setup\\make_israel_dem.py
Source: AWS Open Data "Terrain Tiles" (SRTM, public domain), one 1x1 degree .hgt.gz per tile.
The mosaic is WGS 84 geographic metres-of-elevation; the NoiseBox tools clip and project it themselves.
"""
import glob
import gzip
import os
import shutil
import tempfile
import urllib.error
import urllib.request

import arcpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "dem")
TILES = ["N%dE%03d" % (lat, lon) for lat in range(29, 34) for lon in (34, 35)]
URL = "https://s3.amazonaws.com/elevation-tiles-prod/skadi/N{lat}/{name}.hgt.gz"


def main():
    os.makedirs(OUT, exist_ok=True)
    arcpy.env.overwriteOutput = True
    work = tempfile.mkdtemp(prefix="nb_dem_")
    tifs = []
    try:
        for name in TILES:
            gz = os.path.join(work, name + ".hgt.gz")
            try:
                urllib.request.urlretrieve(URL.format(lat=name[1:3], name=name), gz)
            except urllib.error.HTTPError as e:
                print("skip", name, e.code)
                continue
            hgt = os.path.join(work, name + ".hgt")
            with gzip.open(gz, "rb") as fi, open(hgt, "wb") as fo:
                shutil.copyfileobj(fi, fo)
            tif = os.path.join(work, name + ".tif")
            arcpy.management.CopyRaster(hgt, tif)
            arcpy.management.SetRasterProperties(tif, nodata=[[1, -32768]])
            tifs.append(tif)
            print("ok", name)
        arcpy.management.MosaicToNewRaster(tifs, OUT, "Israel_SRTM_30m.tif", pixel_type="16_BIT_SIGNED",
                                           number_of_bands=1, mosaic_method="LAST")
        arcpy.management.SetRasterProperties(os.path.join(OUT, "Israel_SRTM_30m.tif"), nodata=[[1, -32768]])
        print("Created", os.path.join(OUT, "Israel_SRTM_30m.tif"))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
