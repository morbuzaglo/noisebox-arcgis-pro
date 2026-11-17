dem/Israel_SRTM_30m.tif  - SRTM 1 arc-second (~30 m) elevation, mosaic of 10 tiles N29-N33 / E034-E035,
                           WGS 84 geographic, metres, NoData -32768 (SRTM voids; sea tiles hold 0/void artefacts).
Source: AWS Open Data "Terrain Tiles" (Mapzen/SRTM): https://s3.amazonaws.com/elevation-tiles-prod/skadi/N32/N32E034.hgt.gz
        (one gz per 1x1 degree tile). Downloaded 2026-11-17. Public domain (NASA/USGS SRTM).
Use as the DEM input of the NoiseBox tools; they clip and project it to the sources' CRS automatically.
