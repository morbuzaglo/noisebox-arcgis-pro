"""Scenario model: the single, versioned description of one noise-mapping case.

The ArcGIS Pro add-in (C#) edits this JSON; this module validates it, resolves it to the analysis coordinate system and
hands it to the pipeline. Acoustics are NOT here: they stay in matlab/core (called through worker/matlab_glue/nb_job.m).

arcpy is imported lazily, so everything that does not need GIS data (parsing, geometry checks, most validation) runs in
any Python.
"""
import copy
import csv
import json
import math
import os
import re
import uuid
from datetime import datetime

from . import config, issues as I, structures as S
from .config import BANDS, NoiseBoxError

SCHEMA = "noisebox.scenario/1"
MODES = {
    "iso2024": "ISO 9613-2:2024 (default)",
    "draft2026": "draft amendment to ISO 9613-2:2024 (not a published edition)",
    "iso1996": "ISO 9613-2:1996 (superseded edition)",
}
FT = 0.3048
MAX_STRUCTURES = 500
MAX_CELLS_SOURCES = 2_000_000
MAX_DETAIL_CELLS = 100_000
SECONDS_PER_CELL_SOURCE = 0.007
KNOWN_TOP = {"schema", "id", "name", "created", "modified", "notes", "crs", "source", "terrain", "area", "structures",
             "propagation", "outputs"}


# ------------------------------------------------------------------ construction, files
def new_scenario(name="Scenario 1", wkid=None):
    """Empty scenario. Physical constants have defaults; project-specific inputs (location, height, spectrum, area)
    are empty on purpose so that Preview says exactly what is missing."""
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "schema": SCHEMA, "id": uuid.uuid4().hex[:12], "name": name, "created": now, "modified": now, "notes": "",
        "crs": {"wkid": wkid},
        "source": {
            "name": "Source 1", "origin": None, "x": None, "y": None, "input_wkid": None, "layer": None,
            "height_m": None,
            "spectrum": {"lw": [None] * 8, "profile": None, "kind": "manual"},
            "directivity": {"mode": "omni", "dc": [None] * 8, "heading_deg": 0.0, "angular_table": None},
        },
        "terrain": {"dtm": None, "vertical_unit": None, "screening": True},
        "area": {"mode": None, "rings": None, "radius_m": None, "extent": None, "input_wkid": None, "layer": None,
                 "selection": None, "cell": {"mode": "custom", "size_m": None}, "receiver_height_m": 1.5},
        "structures": [],
        "propagation": {
            "mode": "iso2024",
            "ground": {"G": 0.5, "separate": False, "Gs": None, "Gm": None, "Gr": None, "mapped": None},
            "atmosphere": {"T_C": 15.0, "RH": 70.0, "p_kPa": 101.325},
            "meteorology": {"method": "favourable", "C0": None},
        },
        "outputs": {"gdb": None, "run_name": None, "overall_a": True, "overall_z": False, "bands": [],
                    "add_to_map": True, "limit_dba": None, "limit_bands": [None] * 8, "limit_band_weighting": "A", "shared_scale": None, "detail": "Levels only",
                    "inside_buildings": "nodata"},
    }


def duplicate(sc, new_name=None):
    d = copy.deepcopy(sc)
    d["id"] = uuid.uuid4().hex[:12]
    d["name"] = new_name or (sc.get("name", "Scenario") + " copy")
    d["created"] = d["modified"] = datetime.now().isoformat(timespec="seconds")
    return d


def save(sc, path):
    sc = dict(sc)
    sc["modified"] = datetime.now().isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sc, f, indent=2)
    return path


def load(path):
    """-> (scenario or None, [Issue])."""
    if not os.path.isfile(path):
        return None, [I.make("SCN-001", path=path)]
    try:
        with open(path, "r", encoding="utf-8") as f:
            sc = json.load(f)
    except (ValueError, OSError) as e:
        return None, [I.make("SCN-002", detail=str(e)[:120])]
    out = []
    if not isinstance(sc, dict) or sc.get("schema") != SCHEMA:
        found = sc.get("schema") if isinstance(sc, dict) else type(sc).__name__
        return None, [I.make("SCN-003", found=found, expected=SCHEMA)]
    extra = sorted(set(sc) - KNOWN_TOP)
    if extra:
        out.append(I.make("SCN-005", keys=", ".join(extra)))
    return sc, out


# ------------------------------------------------------------------ coordinate systems
_KNOWN = {
    4326: ("WGS 84", "Geographic"), 4258: ("ETRS89", "Geographic"), 4269: ("NAD 83", "Geographic"),
    4230: ("ED50", "Geographic"), 4619: ("SWEREF99", "Geographic"), 6991: ("Israel 1993", "Geographic"),
    2039: ("Israeli TM Grid", "Projected"), 3857: ("Web Mercator", "Projected"),
}


def crs_info(wkid):
    """-> dict(wkid, name, type 'Geographic'|'Projected', unit, mpu, labels). Uses arcpy when available."""
    try:
        import arcpy
        sr = arcpy.SpatialReference(int(wkid))
        if sr.type in ("Geographic", "Projected"):
            geo = sr.type == "Geographic"
            return {"wkid": int(wkid), "name": sr.name, "type": sr.type,
                    "unit": "degrees" if geo else sr.linearUnitName,
                    "mpu": None if geo else sr.metersPerUnit, **_labels(geo, sr.linearUnitName)}
    except Exception:
        pass
    if wkid in _KNOWN:
        nm, ty = _KNOWN[wkid]
        geo = ty == "Geographic"
        return {"wkid": int(wkid), "name": nm, "type": ty, "unit": "degrees" if geo else "metre",
                "mpu": None if geo else 1.0, **_labels(geo, "metre")}
    if 32601 <= wkid <= 32660 or 32701 <= wkid <= 32760:
        return {"wkid": int(wkid), "name": "WGS 84 / UTM", "type": "Projected", "unit": "metre", "mpu": 1.0,
                **_labels(False, "metre")}
    return None


def _labels(geographic, unit):
    if geographic:
        return {"label_x": "Longitude", "label_y": "Latitude", "order": "Longitude, Latitude",
                "unit_text": "decimal degrees (east positive, north positive)"}
    return {"label_x": "Easting", "label_y": "Northing", "order": "Easting, Northing",
            "unit_text": "%s" % (unit or "metres").lower()}


def coordinate_labels(wkid):
    """Field labels, expected order and unit for the coordinate fields of a coordinate system."""
    info = crs_info(wkid)
    if info is None:
        raise NoiseBoxError("Unknown coordinate system %s." % wkid)
    return {k: info[k] for k in ("label_x", "label_y", "order", "unit_text", "name", "type")}


def suggest_projected(lon, lat):
    """A metre-based projected CRS for a lon/lat (Israel TM for Israel and the Palestinian territories, else UTM)."""
    if 34.0 <= lon <= 36.0 and 29.3 <= lat <= 33.5:
        return 2039
    zone = int((lon + 180.0) // 6.0) + 1
    return (32600 if lat >= 0 else 32700) + max(1, min(60, zone))


def transform_xy(x, y, from_wkid, to_wkid):
    if from_wkid == to_wkid or from_wkid is None:
        return float(x), float(y)
    import arcpy
    g = arcpy.PointGeometry(arcpy.Point(float(x), float(y)), arcpy.SpatialReference(int(from_wkid)))
    p = g.projectAs(arcpy.SpatialReference(int(to_wkid)))
    if p is None or p.firstPoint is None:
        raise NoiseBoxError("The point (%s, %s) cannot be converted from %s to %s." % (x, y, from_wkid, to_wkid))
    return p.firstPoint.X, p.firstPoint.Y


def safe_source_xy(sc, wkid):
    """Source position in the analysis CRS, or None when it is missing or cannot be converted."""
    s = sc.get("source") or {}
    if not (_finite(s.get("x")) and _finite(s.get("y"))) or not wkid:
        return None
    try:
        return source_xy(sc, wkid)
    except Exception:
        return None


def transform_rings(rings, from_wkid, to_wkid):
    if from_wkid == to_wkid or from_wkid is None:
        return [[(float(x), float(y)) for x, y in r] for r in rings]
    return [[transform_xy(x, y, from_wkid, to_wkid) for x, y in r] for r in rings]


# ------------------------------------------------------------------ the three ways to define the source
def source_from_coords(x, y, wkid):
    """Enter Coordinates: values typed or pasted in coordinate system `wkid`."""
    return {"origin": "coords", "x": float(x), "y": float(y), "input_wkid": int(wkid), "layer": None}


def source_from_map(x, y, wkid):
    """Place on Map: the click position in the map's coordinate system."""
    return {"origin": "map", "x": float(x), "y": float(y), "input_wkid": int(wkid), "layer": None}


def source_from_layer(layer, selection="selected", key=None, key_field=None):
    """From Layer: a point feature of `layer` (a path or layer object).

    selection: "selected" (the one selected feature; if several are selected the first by OID is used and the others
    are reported by the caller), "key" (matches `key` against `key_field`, or the OID when key_field is None).
    -> (dict for scenario['source'], [matching OIDs]).
    """
    import arcpy
    desc = arcpy.Describe(layer)
    if desc.shapeType != "Point":
        raise NoiseBoxError(I.make("SRC-007", layer=getattr(desc, "name", layer), shape=desc.shapeType).message)
    sr = desc.spatialReference
    if sr is None or sr.type == "Unknown":
        raise NoiseBoxError(I.make("SRC-011", layer=desc.name).message)
    oid_f = desc.OIDFieldName
    sel = list(getattr(desc, "FIDSet", "").split(";")) if getattr(desc, "FIDSet", "") else []
    if selection == "selected":
        wanted = sorted(int(v) for v in sel)
        where = "%s IN (%s)" % (oid_f, ",".join(map(str, wanted))) if wanted else None
        if where is None:
            raise NoiseBoxError(I.make("SRC-006", layer=desc.name).message)
    else:
        f = key_field or oid_f
        q = "'%s'" % str(key).replace("'", "''") if key_field and not _is_numeric_field(layer, key_field) else key
        where = "%s = %s" % (arcpy.AddFieldDelimiters(layer, f), q)
    rows = []
    with arcpy.da.SearchCursor(layer, ["OID@", "SHAPE@XY"], where) as cur:
        for oid, xy in cur:
            if xy is not None:
                rows.append((oid, xy))
    if not rows:
        raise NoiseBoxError(I.make("SRC-010", key=key, layer=desc.name).message if selection != "selected"
                            else I.make("SRC-012").message)
    oid, (x, y) = sorted(rows)[0]
    return ({"origin": "layer", "x": float(x), "y": float(y), "input_wkid": int(sr.factoryCode),
             "layer": {"path": desc.catalogPath, "name": desc.name, "oid": int(oid)}}, [r[0] for r in sorted(rows)])


def _is_numeric_field(layer, name):
    import arcpy
    for f in arcpy.ListFields(layer, name):
        return f.type in ("Integer", "SmallInteger", "Double", "Single", "OID")
    return False


# ------------------------------------------------------------------ spectrum input
def _num(t):
    t = t.strip()
    if t == "" or t.lower() in ("nan", "na", "n/a", "-", "--"):
        return None, False
    comma = "," in t and "." not in t
    try:
        return float(t.replace(",", ".")), comma
    except ValueError:
        raise ValueError(t)


def parse_spectrum_text(text):
    """Pasted text (a row or column from Excel/MATLAB, or 2 columns frequency|level) -> (8 values or None, [Issue]).

    Empty cells stay None (missing), which is different from 0 dB."""
    iss = []
    lines = [ln for ln in re.split(r"[\r\n]+", text.strip()) if ln.strip()]
    rows = []
    for ln in lines:
        s = ln.strip().strip("[]")
        if "\t" in s or ";" in s:
            toks = re.split(r"[\t;]", s)
        elif " " in s.strip() and "," not in s.replace(", ", " "):
            toks = re.split(r"\s+", s)
        elif "," in s:
            toks = re.split(r"\s*,\s*", s)           # CSV: a comma separates columns
        else:
            toks = re.split(r"\s+", s)
        try:
            vals = []
            for t in toks:
                v, comma = _num(t)
                if comma:
                    iss.append(I.make("SPC-014", text=t.strip(), value=v))
                vals.append(v)
            rows.append(vals)
        except ValueError:
            if not rows:         # header line
                continue
            return None, [I.make("SPC-003", band="?", value=s[:20])]
    if not rows:
        return None, [I.make("SPC-001")]
    flat = [v for r in rows for v in r]
    band_f = [float(b) for b in BANDS]
    if len(rows) == 1 and len(rows[0]) == 8:
        return rows[0], iss
    if all(len(r) == 1 for r in rows) and len(rows) == 8:
        return [r[0] for r in rows], iss
    if all(len(r) == 2 for r in rows):                                    # frequency | level
        near = [r[0] is not None and any(abs(r[0] - b) <= 0.02 * b for b in BANDS) for r in rows]
        if len(rows) == 8 and not any(near) and all("," in ln and "\t" not in ln and ";" not in ln for ln in lines):
            try:                                                           # a column of comma decimals ("90,5")
                vals = [float(ln.strip().replace(",", ".")) for ln in lines]
                return vals, iss + [I.make("SPC-014", text=lines[0].strip(), value=vals[0])]
            except ValueError:
                pass
        return _by_frequency([(r[0], r[1]) for r in rows], iss)
    if len(rows) == 2 and len(rows[0]) == len(rows[1]):                   # two rows: frequencies, levels
        return _by_frequency(list(zip(rows[0], rows[1])), iss)
    return None, iss + [I.make("SPC-008", n=len(flat))]


def _by_frequency(pairs, iss):
    out = [None] * 8
    for f, v in pairs:
        if f is None:
            continue
        hit = [i for i, b in enumerate(BANDS) if abs(f - b) <= 0.02 * b]
        if not hit:
            return None, iss + [I.make("SPC-010", freq=f)]
        out[hit[0]] = v
    return out, iss


def read_spectrum_csv(path):
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            text = f.read()
    except OSError as e:
        return None, [I.make("SPC-009", path=path, detail=str(e)[:80])]
    vals, iss = parse_spectrum_text(text)
    if vals is None and not any(i.severity == I.ERROR for i in iss):
        iss.append(I.make("SPC-009", path=path, detail="no usable numbers"))
    if vals is not None and any(v is None for v in vals):
        iss.append(I.make("SPC-011", bands=", ".join(str(b) for b, v in zip(BANDS, vals) if v is None)))
    return vals, iss


def profile_dir():
    d = os.environ.get("NOISEBOX_PROFILE_DIR") or os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                                                               "NoiseBox", "profiles")
    os.makedirs(d, exist_ok=True)
    return d


def _profile_path(name):
    return os.path.join(profile_dir(), re.sub(r"[^\w\-. ]", "_", name.strip()) + ".json")


def save_profile(name, lw, dc=None):
    if not name or not name.strip():
        raise NoiseBoxError(I.make("SPC-013").message)
    with open(_profile_path(name), "w", encoding="utf-8") as f:
        json.dump({"name": name.strip(), "bands": list(BANDS), "lw": lw, "dc": dc}, f, indent=2)
    return _profile_path(name)


def load_profile(name):
    p = _profile_path(name)
    if not os.path.isfile(p):
        raise NoiseBoxError(I.make("SPC-012", name=name).message)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def list_profiles():
    return sorted(os.path.splitext(f)[0] for f in os.listdir(profile_dir()) if f.lower().endswith(".json"))


# ------------------------------------------------------------------ resolution to the analysis CRS
def analysis_wkid(sc):
    """crs.wkid, else the source's CRS if it is projected metres, else a suggestion for a geographic source."""
    w = (sc.get("crs") or {}).get("wkid")
    if w:
        return int(w)
    s = sc.get("source") or {}
    iw = s.get("input_wkid")
    if iw and s.get("x") is not None:
        info = crs_info(iw)
        if info and info["type"] == "Projected":
            return int(iw)
        if info and info["type"] == "Geographic" and _finite(s.get("x")) and _finite(s.get("y")):
            return suggest_projected(s["x"], s["y"])
    return None


def _finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def source_xy(sc, wkid=None):
    """Source position in the analysis CRS."""
    s = sc["source"]
    wkid = wkid or analysis_wkid(sc)
    return transform_xy(s["x"], s["y"], s.get("input_wkid") or wkid, wkid)


def area_rings(sc, wkid=None):
    """Receiver area -> (list of rings in the analysis CRS, bbox) or (None, None)."""
    a = sc["area"]
    wkid = wkid or analysis_wkid(sc)
    mode = a.get("mode")
    if mode == "polygon" and a.get("rings"):
        rings = [S.clean_ring(r) for r in transform_rings(a["rings"], a.get("input_wkid") or wkid, wkid)]
        rings = [r for r in rings if len(r) >= 3]
        if rings:
            return rings, S.bbox_of([p for r in rings for p in r])
    elif mode == "radius" and _finite(a.get("radius_m")) and a["radius_m"] > 0 and _finite(sc["source"].get("x")):
        cx, cy = source_xy(sc, wkid)
        r = float(a["radius_m"])
        n = 180
        ring = [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
        return [ring], (cx - r, cy - r, cx + r, cy + r)
    elif mode == "extent" and a.get("extent") and len(a["extent"]) == 4:
        x0, y0, x1, y1 = [float(v) for v in a["extent"]]
        iw = a.get("input_wkid") or wkid
        if iw != wkid:
            pts = transform_rings([[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]], iw, wkid)[0]
            bb = S.bbox_of(pts)
            x0, y0, x1, y1 = bb
        if x1 > x0 and y1 > y0:
            return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]], (x0, y0, x1, y1)
    return None, None


def dtm_info(path):
    """Describe a raster for the pane: native cell (m), CRS, vertical unit as stored, extent."""
    import arcpy
    d = arcpy.Describe(path)
    sr = d.spatialReference
    geo = sr is not None and sr.type == "Geographic"
    vunit = None
    try:
        if sr is not None and sr.VCS is not None and sr.VCS.name:
            vunit = (sr.VCS.linearUnitName or "").lower() or None
    except Exception:
        vunit = None
    return {"path": path, "name": d.baseName, "bands": d.bandCount, "wkid": sr.factoryCode if sr else None,
            "crs_name": sr.name if sr else None, "crs_type": sr.type if sr else None,
            "cell_x": d.meanCellWidth, "cell_y": d.meanCellHeight,
            "cell_m": d.meanCellHeight * (111320.0 if geo else (sr.metersPerUnit if sr else 1.0)),
            "extent": [d.extent.XMin, d.extent.YMin, d.extent.XMax, d.extent.YMax],
            "vertical_unit": vunit, "pixel_type": d.pixelType}


def dtm_unit_factor(sc, info=None):
    """(factor to metres, unit text, detected) or (None, None, None) when the vertical unit is unknown."""
    t = sc["terrain"]
    u = (t.get("vertical_unit") or "").lower()
    if u in ("m", "metre", "meter", "metres", "meters"):
        return 1.0, "metres", False
    if u in ("ft", "foot", "feet", "us ft"):
        return FT, "feet", False
    det = (info or {}).get("vertical_unit") or ""
    if det.startswith("met"):
        return 1.0, "metres", True
    if det.startswith("foot") or det.startswith("feet") or "ft" in det:
        return FT, "feet", True
    return None, None, None


def cell_size(sc, info=None):
    c = sc["area"]["cell"]
    if c.get("mode") == "match_dtm":
        return round(info["cell_m"], 3) if info else None
    return float(c["size_m"]) if _finite(c.get("size_m")) and c["size_m"] > 0 else None


def estimate(sc, info=None):
    """Receiver grid size without any calculation. -> dict(cell, nx, ny, cells, active, minutes) or None."""
    rings, bb = area_rings(sc)
    cs = cell_size(sc, info)
    if rings is None or not cs:
        return None
    nx = max(1, int(math.ceil((bb[2] - bb[0]) / cs - 1e-9)))
    ny = max(1, int(math.ceil((bb[3] - bb[1]) / cs - 1e-9)))
    total = nx * ny
    if sc["area"].get("mode") == "polygon" and len(rings) >= 1:
        frac = min(1.0, sum(S.ring_area(r) for r in rings) / max(1e-9, (bb[2] - bb[0]) * (bb[3] - bb[1])))
    elif sc["area"].get("mode") == "radius":
        frac = math.pi / 4.0
    else:
        frac = 1.0
    active = int(total * frac)
    return {"cell": cs, "nx": nx, "ny": ny, "cells": total, "active": active,
            "minutes": ny * nx * SECONDS_PER_CELL_SOURCE / 60.0 + 0.3}


# ------------------------------------------------------------------ materials
def _bands_text(idx):
    return ", ".join(str(BANDS[i]) for i in idx)


def face_names(enc, src_xy):
    """Names of the faces of an enclosure, from its footprint (walls by compass direction, then Roof)."""
    ring = enclosure_ring(enc, src_xy)
    return [f["name"] for f in S.enclosure_faces(ring, enc.get("height_m") or 1.0)] if ring else []


def enclosure_ring(enc, src_xy, wkid=None):
    """Footprint of an enclosure in the analysis CRS (a drawn footprint is converted from its own `input_wkid`)."""
    if enc.get("mode") == "rectangle":
        r = enc.get("rect") or {}
        if not all(_finite(r.get(k)) and r[k] > 0 for k in ("length_m", "width_m")) or not _finite(r.get("orientation_deg", 0)):
            return None
        off = r.get("offset") or [0.0, 0.0]
        if src_xy is None or not all(_finite(v) for v in off):
            return None
        c = (src_xy[0] + off[0], src_xy[1] + off[1])
        return S.rect_footprint(c, r["length_m"], r["width_m"], r.get("orientation_deg", 0.0))
    pts = enc.get("footprint") or []
    if pts and wkid and enc.get("input_wkid") and enc["input_wkid"] != wkid:
        pts = transform_rings([pts], enc["input_wkid"], wkid)[0]
    fp = S.clean_ring(pts)
    return fp if len(fp) >= 3 else None


def face_material(enc, face):
    f = enc.get("faces") or {}
    if f.get("mode") == "per_face":
        return (f.get("faces") or {}).get(face)
    return f.get("all")


def _mat_job(fm):
    """Face material -> core material struct (nb_material input)."""
    if fm["mode"] == "manufacturer":
        return {"surface_mass": None, "volume_density": None, "thickness": None, "solid": None,
                "TL": [float(v) for v in fm["TL"]], "openness": None, "tl_model": None}
    return {"surface_mass": fm.get("surface_mass_kg_m2"), "volume_density": fm.get("volume_density_kg_m3"),
            "thickness": fm.get("thickness_m"), "solid": bool(fm.get("solid")), "TL": None, "openness": None,
            "tl_model": fm.get("tl_model") or "normal"}


def barrier_material_job(b):
    tr = b.get("transmission") or {}
    if not tr.get("enabled"):
        return None
    return _mat_job(tr["material"])


def enclosure_job(enc, src_xy, wkid=None):
    """Enclosure -> {"surfaces": [...], "S_open": ...} for the core, plus (ring, faces)."""
    ring = enclosure_ring(enc, src_xy, wkid)
    faces = S.enclosure_faces(ring, enc["height_m"])
    surf = []
    for f in faces:
        fm = face_material(enc, f["name"])
        surf.append({"name": f["name"], "area": f["area"], "mat": _mat_job(fm), "alpha": [float(v) for v in fm["alpha"]]})
    return {"surfaces": surf, "S_open": float(enc.get("open_area_m2") or 0.0)}, ring, faces


# ------------------------------------------------------------------ validation
class _Ctx:
    def __init__(self, sc):
        self.sc = sc
        self.issues = []

    def add(self, code, **kw):
        self.issues.append(I.make(code, **kw))


def validate(sc, deep=True, info=None):
    """All problems with a scenario, as Issue objects (errors first). deep=True also reads the DTM / layers / gdb."""
    c = _Ctx(sc)
    _v_scenario(c)
    wkid = _v_crs(c)
    _v_source(c, wkid)
    _v_spectrum(c)
    _v_directivity(c)
    dtm = _v_terrain(c, wkid, deep, info)
    _v_area(c, wkid, dtm)
    _v_structures(c, wkid, dtm)
    _v_propagation(c)
    _v_outputs(c, deep)
    if deep:
        _v_engine(c)
    return I.sort_issues(c.issues)


def _v_scenario(c):
    sc = c.sc
    if sc.get("schema") != SCHEMA:
        c.add("SCN-003", found=sc.get("schema"), expected=SCHEMA)
    if not (sc.get("name") or "").strip():
        c.add("SCN-004")


def _v_crs(c):
    sc = c.sc
    w = analysis_wkid(sc)
    if not w:
        c.add("SCN-006")
        return None
    info = crs_info(w)
    if info is None:
        c.add("SCN-009", wkid=w)
        return None
    if info["type"] != "Projected":
        s = sc["source"]
        sug = suggest_projected(s["x"], s["y"]) if _finite(s.get("x")) and _finite(s.get("y")) else 2039
        c.add("SCN-007", wkid=w, suggest="%d" % sug)
        return None
    if info["mpu"] is not None and abs(info["mpu"] - 1.0) > 1e-9:
        c.add("SCN-008", wkid=w, unit=info["unit"], mpu=info["mpu"])
        return None
    return w


def _v_source(c, wkid):
    s = c.sc["source"]
    x, y = s.get("x"), s.get("y")
    if x is None and y is None:
        c.add("SRC-001")
    elif not (_finite(x) and _finite(y)):
        c.add("SRC-002", x=x, y=y)
    else:
        iw = s.get("input_wkid")
        info = crs_info(iw) if iw else None
        if iw and info is None:
            c.add("SCN-009", wkid=iw)
        elif info and info["type"] == "Geographic":
            if abs(x) > 180 or abs(y) > 90:
                if abs(y) <= 180 and abs(x) <= 90:
                    c.add("SRC-004", x=x, y=y, order=info["order"])
                c.add("SRC-003", x=x, y=y, wkid=iw, detail="longitude must be within +-180 and latitude within +-90",
                      order=info["order"])
        if wkid and iw and iw != wkid and not any(i.code == "SRC-003" for i in c.issues):
            try:
                px, py = source_xy(c.sc, wkid)
                c.add("SRC-013", from_wkid=iw, to_wkid=wkid, x=px, y=py)
            except Exception:
                pass
    h = s.get("height_m")
    if h is None:
        c.add("SRC-014")
    elif not _finite(h) or h < 0:
        c.add("SRC-015", value=h)
    elif h > 100:
        c.add("SRC-016", value=h)
    elif h == 0:
        c.add("SRC-017")
    if not c.sc["terrain"].get("dtm"):
        c.add("SRC-019")


def _v_spectrum(c):
    sp = c.sc["source"]["spectrum"]
    lw = sp.get("lw") or []
    if not lw or len(lw) != 8:
        c.add("SPC-001")
        return
    missing = [i for i, v in enumerate(lw) if v is None]
    bad = [i for i, v in enumerate(lw) if v is not None and not _finite(v)]
    for i in bad:
        c.add("SPC-003", band=BANDS[i], value=lw[i])
    if missing:
        if len(missing) == 8:
            c.add("SPC-001")
        else:
            c.add("SPC-002", n=len(missing), bands=_bands_text(missing))
        return
    if bad:
        return
    if all(v == 0 for v in lw):
        c.add("SPC-006")
    elif len(set(lw)) == 1:
        c.add("SPC-007", value=lw[0])
    for i, v in enumerate(lw):
        if v < 0:
            c.add("SPC-004", band=BANDS[i], value=v)
        elif v > 160:
            c.add("SPC-005", band=BANDS[i], value=v)
    if sp.get("profile"):
        c.add("SPC-015", kind=sp.get("kind", "manual"), name=sp["profile"])


def _v_directivity(c):
    d = c.sc["source"]["directivity"]
    mode = d.get("mode", "omni")
    hd = d.get("heading_deg", 0.0)
    if not _finite(hd):
        c.add("DIR-005", value=hd)
    elif hd < 0 or hd >= 360:
        c.add("DIR-006", value=hd, norm=hd % 360.0)
    if d.get("angular_table"):
        c.add("DIR-007")
    if mode == "omni":
        c.add("DIR-001")
        return
    dc = d.get("dc") or [None] * 8
    miss = [i for i in range(8) if i >= len(dc) or dc[i] is None]
    if miss:
        c.add("DIR-002", bands=_bands_text(miss))
    for i, v in enumerate(dc[:8]):
        if v is not None and _finite(v) and abs(v) > 20:
            c.add("DIR-003", value=v, band=BANDS[i])
    c.add("DIR-004", heading=hd if _finite(hd) else "?")


def _v_terrain(c, wkid, deep, info):
    """-> dict(info, factor) or None."""
    sc = c.sc
    t = sc["terrain"]
    if not t.get("screening", True) and t.get("dtm"):
        c.add("DTM-016")
    if not t.get("dtm"):
        c.add("DTM-001")
        return None
    path = t["dtm"]["path"] if isinstance(t["dtm"], dict) else t["dtm"]
    if info is None and deep:
        try:
            import arcpy
            if not arcpy.Exists(path):
                c.add("DTM-002", path=path)
                return None
            info = dtm_info(path)
        except ImportError:
            c.add("ENG-015")
            return None
        except Exception:
            c.add("DTM-002", path=path)
            return None
    if info is None:
        return None
    if info["bands"] != 1:
        c.add("DTM-003", path=path, bands=info["bands"])
        return None
    if not info["wkid"] or info["crs_type"] == "Unknown":
        c.add("DTM-004", path=path)
        return None
    factor, unit, detected = dtm_unit_factor(sc, info)
    if factor is None:
        c.add("DTM-006")
    elif factor != 1.0:
        c.add("DTM-007", unit=unit, factor=factor)
    if wkid and info["wkid"] != wkid:
        c.add("DTM-005", dtm_crs=info["crs_name"], to_wkid=wkid)
    cs = cell_size(sc, info)
    if cs and info["cell_m"] > cs * 1.5:
        c.add("DTM-013", dtm_cell=info["cell_m"], cell=cs)
    if info["cell_m"] > 10:
        c.add("DTM-018", dtm_cell=info["cell_m"])
    return {"info": info, "factor": factor or 1.0}


def _v_area(c, wkid, dtm):
    sc = c.sc
    a = sc["area"]
    mode = a.get("mode")
    rh = a.get("receiver_height_m")
    if not _finite(rh) or rh <= 0:
        c.add("ARA-022", value=rh)
    else:
        if rh > 50:
            c.add("ARA-023", value=rh)
        c.add("ARA-024")
    cell = a.get("cell") or {}
    if cell.get("mode") == "match_dtm":
        if not sc["terrain"].get("dtm"):
            c.add("ARA-017")
    elif not _finite(cell.get("size_m")) or cell["size_m"] <= 0:
        c.add("ARA-016", value=cell.get("size_m"))
    if mode is None:
        c.add("ARA-001")
        return
    if mode == "polygon":
        rings = a.get("rings") or []
        if not rings:
            c.add("ARA-002")
            return
        clean = [S.clean_ring(r) for r in rings]
        if any(len(r) < 3 for r in clean):
            c.add("ARA-003")
            return
        for r in clean:
            pt = S.self_intersection(r)
            if pt:
                c.add("ARA-004", x=pt[0], y=pt[1])
                return
            if S.ring_area(r) < 1e-6:
                c.add("ARA-005")
                return
        if len(clean) > 1:
            c.add("ARA-027")
    elif mode == "radius":
        r = a.get("radius_m")
        if not _finite(r) or r <= 0:
            c.add("ARA-008", value=r)
            return
        if r > 20000:
            c.add("ARA-009", value=r, area_km2=math.pi * r * r / 1e6)
        elif r < 10:
            c.add("ARA-010", value=r)
        c.add("ARA-014", value=r)
    elif mode == "extent":
        e = a.get("extent")
        if not e or len(e) != 4 or not all(_finite(v) for v in e) or e[2] <= e[0] or e[3] <= e[1]:
            c.add("ARA-011")
            return
        c.add("ARA-015")
        if a.get("input_wkid") and wkid and a["input_wkid"] != wkid:
            c.add("ARA-012", wkid=a["input_wkid"])
    else:
        c.add("ARA-001")
        return
    if not wkid:
        return
    rings, bb = area_rings(sc, wkid)
    if rings is None:
        return
    sxy0 = safe_source_xy(sc, wkid)
    if sxy0:
        sx, sy = sxy0
        inside = any(S.point_in_ring(sx, sy, r) for r in rings)
        if not inside:
            c.add("ARA-013")
        dist = math.hypot(((bb[0] + bb[2]) / 2) - sx, ((bb[1] + bb[3]) / 2) - sy)
        if dist > 50000:
            c.add("SRC-005", dist_km=dist / 1000.0)
    est = estimate(sc, dtm["info"] if dtm else None)
    if est:
        n_across = min(est["nx"], est["ny"])
        c.add("ARA-030", cell=est["cell"], nx=est["nx"], ny=est["ny"], cells=est["cells"])
        if n_across < 10:
            c.add("ARA-018", cell=est["cell"], n=n_across)
        if est["cells"] > MAX_CELLS_SOURCES:
            c.add("ARA-019", cells=est["cells"], nsrc=1, limit=MAX_CELLS_SOURCES)
        elif est["active"] > MAX_DETAIL_CELLS and c.sc["outputs"].get("detail") == "Full":
            c.add("ARA-020", cells=est["active"], limit=MAX_DETAIL_CELLS)
        if est["minutes"] > 20:
            c.add("ARA-021", minutes=est["minutes"], cells=est["cells"])


def _structure_participation(c, st):
    if st.get("include", True) and not st.get("visible", True):
        c.add("STR-004", object_id=st.get("id", ""), name=st.get("name"))
    elif not st.get("include", True) and st.get("visible", True):
        c.add("STR-005", object_id=st.get("id", ""), name=st.get("name"))


def _ring_issues(c, st, ring, code_few, code_cross, **kw):
    oid = st.get("id", "")
    r = S.clean_ring(ring or [])
    if len(r) < 3:
        c.issues.append(I.make(code_few, object_id=oid, name=st.get("name")))
        return None
    pt = S.self_intersection(r)
    if pt:
        c.issues.append(I.make(code_cross, object_id=oid, name=st.get("name"), x=pt[0], y=pt[1]))
        return None
    return r


def _v_structures(c, wkid, dtm):
    sc = c.sc
    sts = sc.get("structures") or []
    names = {}
    n_inc = 0
    sxy = safe_source_xy(sc, wkid)
    enc_for_source = 0
    rings_for_overlap = []
    for st in sts:
        oid = st.get("id", "")
        nm = (st.get("name") or "").strip()
        if not nm:
            c.add("STR-002", object_id=oid)
        elif nm in names:
            c.add("STR-001", object_id=oid, name=nm)
        names[nm] = True
        t = st.get("type")
        if t not in ("building", "barrier", "enclosure"):
            c.add("STR-003", object_id=oid, name=nm, type=t)
            continue
        _structure_participation(c, st)
        if st.get("include", True):
            n_inc += 1
        else:
            if t == "enclosure":
                c.add("ENC-024", object_id=oid, name=nm)
            else:
                c.add("STR-015", object_id=oid, name=nm)
        if t == "building":
            r = _v_building(c, st, sxy, wkid)
            if r:
                rings_for_overlap.append(r)
        elif t == "barrier":
            _v_barrier(c, st, sxy, wkid, dtm)
        elif t == "enclosure":
            if st.get("include", True):
                enc_for_source += 1
            _v_enclosure(c, st, sxy, wkid)
    if sts:
        c.add("STR-006", n_inc=n_inc, n=len(sts))
    if len(sts) > MAX_STRUCTURES:
        c.add("BLD-019", n=len(sts), limit=MAX_STRUCTURES)
    if enc_for_source > 1:
        c.add("ENC-027", name=sc["source"].get("name"))
    # overlaps between buildings (bounding boxes, cheap)
    n_ov = 0
    for i in range(len(rings_for_overlap)):
        for j in range(i + 1, len(rings_for_overlap)):
            a, b = S.bbox_of(rings_for_overlap[i]), S.bbox_of(rings_for_overlap[j])
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                if any(S.point_in_ring(p[0], p[1], rings_for_overlap[j]) for p in rings_for_overlap[i]):
                    n_ov += 1
    if n_ov:
        c.add("BLD-015", n=n_ov)


def _xf_ring(st, key, wkid):
    iw = st.get("input_wkid") or wkid
    pts = st.get(key) or []
    if not pts:
        return []
    if wkid and iw != wkid:
        return transform_rings([pts], iw, wkid)[0]
    return [(float(p[0]), float(p[1])) for p in pts]


def _v_building(c, st, sxy, wkid):
    oid, nm = st.get("id", ""), st.get("name")
    fp = st.get("footprint")
    if not fp:
        c.add("BLD-001", object_id=oid, name=nm)
        return None
    if any(not (_finite(p[0]) and _finite(p[1])) for p in fp):
        c.add("STR-013", object_id=oid, name=nm, x=fp[0][0], y=fp[0][1])
        return None
    r = _ring_issues(c, st, _xf_ring(st, "footprint", wkid), "BLD-002", "BLD-003")
    h = st.get("height_m")
    if h is None:
        c.add("BLD-004", object_id=oid, name=nm)
    elif not _finite(h) or h <= 0:
        c.add("BLD-005", object_id=oid, name=nm, value=h)
    elif h > 300 or h < 1:
        c.add("BLD-006", object_id=oid, name=nm, value=h)
    if r is None:
        return None
    if S.min_width(r) < 1.0:
        c.add("BLD-018", object_id=oid, name=nm, minw=1.0)
    if st.get("include", True):
        c.add("BLD-017", object_id=oid, name=nm)
        if sxy and S.point_in_ring(sxy[0], sxy[1], r):
            c.add("BLD-012", object_id=oid, name=nm)
    if st.get("layer"):
        c.add("STR-011", object_id=oid, name=nm)
    return r


def _v_barrier(c, st, sxy, wkid, dtm):
    oid, nm = st.get("id", ""), st.get("name")
    pl = st.get("placement") or {}
    path = None
    if pl.get("mode") == "straight":
        miss = [k for k, v in (("start point", pl.get("start")), ("length", pl.get("length_m")),
                               ("azimuth", pl.get("azimuth_deg"))) if v is None]
        if miss:
            c.add("BAR-011", object_id=oid, name=nm, missing=", ".join(miss))
            return
        if not _finite(pl["azimuth_deg"]):
            c.add("BAR-012", object_id=oid, name=nm, value=pl["azimuth_deg"])
            return
        if not _finite(pl["length_m"]) or pl["length_m"] <= 0:
            c.add("BAR-028", object_id=oid, name=nm, value=pl["length_m"])
            return
        iw = st.get("input_wkid") or wkid
        sx, sy = transform_xy(pl["start"][0], pl["start"][1], iw, wkid) if wkid else pl["start"]
        path = S.barrier_from_placement((sx, sy), pl["length_m"], pl["azimuth_deg"])
        c.add("BAR-013", object_id=oid, name=nm, az=pl["azimuth_deg"] % 360.0, x=path[1][0], y=path[1][1])
    else:
        pts = st.get("path")
        if not pts:
            c.add("BAR-001", object_id=oid, name=nm)
            return
        path = S.clean_path(_xf_ring({"input_wkid": st.get("input_wkid"), "p": pts}, "p", wkid))
        if len(path) < 2:
            c.add("BAR-002", object_id=oid, name=nm)
            return
    L = S.path_length(path)
    if L <= 0:
        c.add("BAR-003", object_id=oid, name=nm)
        return
    if L < 3.0:
        c.add("BAR-018", object_id=oid, name=nm, length=L)
    if len(path) > 2:
        c.add("BAR-017", object_id=oid, name=nm, n=len(path) - 1)
    v = st.get("vertical") or {}
    mode = v.get("mode")
    if mode not in ("relative", "absolute"):
        c.add("BAR-007", object_id=oid, name=nm, mode=mode)
        return
    val = v.get("value")
    if val is None:
        c.add("BAR-004", object_id=oid, name=nm)
    elif not _finite(val) or (mode == "relative" and val <= 0):
        c.add("BAR-005", object_id=oid, name=nm, value=val)
    elif mode == "relative" and (val > 15 or val < 0.5):
        c.add("BAR-006", object_id=oid, name=nm, value=val)
    gap = st.get("gap_m")
    if gap not in (None, 0, 0.0) and (not _finite(gap) or gap < 0 or (mode == "relative" and _finite(val) and gap >= val)):
        c.add("BAR-026", object_id=oid, name=nm, gap=gap)
    if sxy:
        d = min(S.dist_point_segment(sxy[0], sxy[1], path[i], path[i + 1]) for i in range(len(path) - 1))
        if d < 1.0:
            c.add("BAR-015", object_id=oid, name=nm)
    tr = st.get("transmission") or {}
    if tr.get("enabled"):
        fm = tr.get("material")
        if not fm:
            c.add("BAR-022", object_id=oid, name=nm)
        else:
            _v_material(c, st, "barrier", fm, need_alpha=False, label=nm)
            m = _mass_of(fm)
            if m is not None and m < 10:
                c.add("BAR-023", object_id=oid, name=nm, m=m)
        c.add("BAR-025", object_id=oid, name=nm)
        kind = "diffraction plus transmission"
    else:
        c.add("BAR-024", object_id=oid, name=nm)
        kind = "diffraction only"
    c.add("BAR-019", object_id=oid, name=nm, kind=kind)
    c.add("STR-012", object_id=oid, name=nm, extra=" and transmission" if tr.get("enabled") else "")
    if st.get("edited"):
        c.add("BAR-027", object_id=oid, name=nm)


def _mass_of(fm):
    if fm.get("mode") == "mass_law":
        if _finite(fm.get("surface_mass_kg_m2")):
            return fm["surface_mass_kg_m2"]
        if _finite(fm.get("thickness_m")) and _finite(fm.get("volume_density_kg_m3")):
            return fm["thickness_m"] * fm["volume_density_kg_m3"]
    return None


def _v_material(c, st, face, fm, need_alpha, label):
    """TL / mass law / alpha checks for one face (or the barrier)."""
    oid, nm = st.get("id", ""), label
    mode = fm.get("mode")
    if mode == "manufacturer":
        tl = fm.get("TL") or [None] * 8
        miss = [i for i in range(8) if i >= len(tl) or tl[i] is None]
        if miss:
            c.add("ENC-009", object_id=oid, name=nm, face=face, bands=_bands_text(miss))
        for i, v in enumerate(tl[:8]):
            if v is None:
                continue
            if not _finite(v) or v < 0:
                c.add("ENC-012", object_id=oid, name=nm, face=face, band=BANDS[i], value=v)
            elif v > 80:
                c.add("ENC-013", object_id=oid, name=nm, face=face, band=BANDS[i], value=v)
    elif mode == "mass_law":
        m, t, rho = fm.get("surface_mass_kg_m2"), fm.get("thickness_m"), fm.get("volume_density_kg_m3")
        if m is None and t is None and rho is None:
            c.add("ENC-014", object_id=oid, name=nm, face=face)
        elif m is not None:
            if not _finite(m) or m <= 0:
                c.add("ENC-015", object_id=oid, name=nm, face=face, value=m)
            elif m < 5 and need_alpha:
                c.add("ENC-019", object_id=oid, name=nm, face=face, m=m)
        else:
            if not (_finite(t) and t > 0 and _finite(rho) and rho > 0):
                c.add("ENC-016", object_id=oid, name=nm, face=face, t=t, rho=rho)
            elif not fm.get("solid"):
                c.add("ENC-017", object_id=oid, name=nm, face=face)
        c.add("ENC-018", object_id=oid, name=nm, face=face)
    else:
        c.add("ENC-014", object_id=oid, name=nm, face=face)
    if need_alpha:
        al = fm.get("alpha") or [None] * 8
        miss = [i for i in range(8) if i >= len(al) or al[i] is None]
        if miss:
            c.add("ENC-010", object_id=oid, name=nm, face=face, bands=_bands_text(miss))
        for i, v in enumerate(al[:8]):
            if v is not None and (not _finite(v) or v < 0 or v > 1):
                c.add("ENC-011", object_id=oid, name=nm, face=face, band=BANDS[i], value=v)


def _v_enclosure(c, st, sxy, wkid):
    oid, nm = st.get("id", ""), st.get("name")
    if st.get("source_link") not in ("source", c.sc["source"].get("name")):
        c.add("ENC-001", object_id=oid, name=nm)
    h = st.get("height_m")
    if not _finite(h) or h <= 0:
        c.add("ENC-034", object_id=oid, name=nm, h=h)
    mode = st.get("mode")
    if mode == "rectangle":
        r = st.get("rect") or {}
        if not all(_finite(r.get(k)) and r[k] > 0 for k in ("length_m", "width_m")) or not _finite(h) or h <= 0:
            c.add("ENC-003", object_id=oid, name=nm, l=r.get("length_m"), w=r.get("width_m"), h=h)
            return
        if not _finite(r.get("orientation_deg", 0.0)):
            c.add("ENC-026", object_id=oid, name=nm, value=r.get("orientation_deg"))
            return
        off = r.get("offset") or [0.0, 0.0]
        if len(off) != 2 or not all(_finite(v) for v in off):
            c.add("ENC-031", object_id=oid, name=nm, dx=off[0] if off else None, dy=off[1] if len(off) > 1 else None)
            return
    elif mode == "polygon":
        if not st.get("footprint"):
            c.add("ENC-002", object_id=oid, name=nm)
            return
        if _ring_issues(c, st, st.get("footprint"), "ENC-002", "ENC-033") is None:
            return
    else:
        c.add("ENC-002", object_id=oid, name=nm)
        return
    ring = enclosure_ring(st, sxy, wkid)
    if ring is None:
        if mode == "polygon":
            c.add("ENC-002", object_id=oid, name=nm)
        return
    if sxy:
        if not S.point_in_ring(sxy[0], sxy[1], ring):
            c.add("ENC-004", object_id=oid, name=nm, dx=S.dist_point_ring(sxy[0], sxy[1], ring))
        else:
            d = S.dist_point_ring(sxy[0], sxy[1], ring)
            if d < 0.3:
                c.add("ENC-006", object_id=oid, name=nm, dist=d)
    hs = c.sc["source"].get("height_m")
    if _finite(hs) and _finite(h) and hs > h:
        c.add("ENC-005", object_id=oid, name=nm, hs=hs, h=h)
    faces = S.enclosure_faces(ring, h) if _finite(h) and h > 0 else []
    if not faces:
        c.add("ENC-032", object_id=oid, name=nm)
        return
    c.add("ENC-030", object_id=oid, name=nm)
    c.add("ENC-035", object_id=oid, name=nm)
    c.add("STR-012", object_id=oid, name=nm, extra="")
    total = sum(f["area"] for f in faces)
    op = st.get("open_area_m2") or 0.0
    if not _finite(op) or op < 0 or op > total:
        c.add("ENC-020", object_id=oid, name=nm, open=op, total=total)
    elif op > 0:
        c.add("ENC-021", object_id=oid, name=nm, open=op, limit=-10 * math.log10(op / total))
    estimated, measured = [], []
    for f in faces:
        fm = face_material(st, f["name"])
        if fm is None:
            c.add("ENC-007" if f["kind"] == "roof" else "ENC-008", object_id=oid, name=nm, wall=f["name"])
            continue
        _v_material(c, st, f["name"], fm, need_alpha=True, label=nm)
        (estimated if fm.get("mode") == "mass_law" else measured).append(f["name"])
    if estimated and measured:
        c.add("ENC-028", object_id=oid, name=nm, face=", ".join(estimated))
    c.add("ENC-023", object_id=oid, name=nm)


def _v_propagation(c):
    p = c.sc["propagation"]
    g = p["ground"]
    if g.get("separate"):
        for k in ("Gs", "Gm", "Gr"):
            v = g.get(k)
            if v is None:
                c.add("PRP-002", which={"Gs": "at the source", "Gm": "in the middle", "Gr": "at the receiver"}[k])
            elif not _finite(v) or not 0 <= v <= 1:
                c.add("PRP-001", value=v)
        if all(g.get(k) is not None and _finite(g[k]) for k in ("Gs", "Gm", "Gr")):
            c.add("PRP-004", gs=g["Gs"], gm=g["Gm"], gr=g["Gr"])
    else:
        v = g.get("G")
        if not _finite(v) or not 0 <= v <= 1:
            c.add("PRP-001", value=v)
        else:
            c.add("PRP-003", value=v)
    if g.get("mapped"):
        c.add("PRP-022")
    a = p["atmosphere"]
    T, RH, pk = a.get("T_C"), a.get("RH"), a.get("p_kPa")
    if not _finite(T) or not -40 <= T <= 50:
        c.add("PRP-005", value=T)
    if not _finite(RH) or not 0 < RH <= 100:
        c.add("PRP-006", value=RH)
    elif RH < 10:
        c.add("PRP-009", value=RH)
    if not _finite(pk) or pk <= 0:
        c.add("PRP-007", value=pk)
    elif not 80 <= pk <= 110:
        c.add("PRP-008", value=pk)
    mode = p.get("mode")
    if mode not in MODES:
        c.add("PRP-010", value=mode)
    else:
        c.add("PRP-011", mode=mode, desc=MODES[mode])
        if mode == "draft2026":
            c.add("PRP-012")
        if mode == "iso1996":
            c.add("PRP-013")
    m = p["meteorology"]
    meth = m.get("method", "favourable")
    C0 = m.get("C0")
    if meth == "long_term":
        if C0 is None:
            c.add("PRP-015")
        elif not _finite(C0) or C0 < 0:
            c.add("PRP-016", value=C0)
        else:
            if C0 > 5:
                c.add("PRP-017", value=C0)
            c.add("PRP-018", value=C0)
    else:
        c.add("PRP-014")
        if C0 not in (None, 0, 0.0):
            c.add("PRP-019")
    c.add("PRP-020", effects=", ".join(active_effects(c.sc)))
    c.add("PRP-021")


def active_effects(sc):
    """Which propagation terms and structure effects the run will use (a plain list of phrases)."""
    p = sc["propagation"]
    eff = ["geometric divergence (Adiv)", "atmospheric absorption (Aatm)", "ground effect (Agr)"]
    inc = [s for s in sc.get("structures", []) if s.get("include", True)]
    nb = sum(1 for s in inc if s["type"] == "building")
    nbar = sum(1 for s in inc if s["type"] == "barrier")
    nenc = sum(1 for s in inc if s["type"] == "enclosure")
    if sc["terrain"].get("dtm"):
        eff.append("terrain elevations and terrain diffraction")
    if nb or nbar:
        eff.append("screening by %d building(s) and %d barrier(s) (Abar)" % (nb, nbar))
    if any(s["type"] == "barrier" and (s.get("transmission") or {}).get("enabled") for s in inc):
        eff.append("transmission through barriers")
    if nenc:
        eff.append("source enclosure (reduced radiated power)")
    if (sc["source"]["directivity"].get("mode") == "directional"):
        eff.append("directivity correction Dc")
    if p["meteorology"].get("method") == "long_term":
        eff.append("long-term meteorological correction C_met")
    return eff


def _v_outputs(c, deep):
    o = c.sc["outputs"]
    gdb = o.get("gdb")
    if not gdb:
        c.add("OUT-001")
    else:
        if not str(gdb).lower().rstrip("\\/").endswith(".gdb"):
            c.add("OUT-003", path=gdb)
        elif deep:
            ok = os.path.isdir(gdb)
            try:
                import arcpy
                ok = bool(arcpy.Exists(gdb)) and ok
            except ImportError:
                pass
            if not ok:
                c.add("OUT-002", path=gdb)
            elif not os.access(gdb, os.W_OK):
                c.add("OUT-004", path=gdb, detail="no write permission")
            if "onedrive" in str(gdb).lower() or "dropbox" in str(gdb).lower():
                c.add("OUT-018", detail="OneDrive/Dropbox")
    rn = (o.get("run_name") or "").strip()
    if not rn:
        c.add("OUT-005")
    else:
        valid = re.sub(r"[^A-Za-z0-9_]", "_", rn)
        if valid[0:1].isdigit():
            valid = "R_" + valid
        if valid != rn:
            c.add("OUT-006", name=rn, valid=valid)
        if len(valid) > 50:
            c.add("OUT-019", name=rn)
    if not (o.get("overall_a") or o.get("overall_z") or o.get("bands")):
        c.add("OUT-008")
    for b in o.get("bands") or []:
        if b not in BANDS:
            c.add("OUT-009", value=b)
    if o.get("bands"):
        c.add("OUT-010")
    ss = o.get("shared_scale")
    if ss and (ss.get("min") is not None or ss.get("max") is not None) and not (
            _finite(ss.get("min")) and _finite(ss.get("max")) and ss["min"] < ss["max"]):
        c.add("OUT-012", vmin=ss.get("min"), vmax=ss.get("max"))
    lim = o.get("limit_dba")
    if lim is not None and not _finite(lim):
        c.add("OUT-014", value=lim)
    lb = o.get("limit_bands")
    if lb is not None:
        if not isinstance(lb, (list, tuple)) or len(lb) != 8:
            c.add("OUT-020", n=(len(lb) if isinstance(lb, (list, tuple)) else "not a list"))
        else:
            for hz, v in zip(BANDS, lb):
                if v is not None and not _finite(v):
                    c.add("OUT-021", band=hz, value=v)
    if o.get("limit_band_weighting", "A") not in ("A", "Z"):
        c.add("OUT-022", value=o.get("limit_band_weighting"))
    if limits_set(o):
        c.add("OUT-023", rule=limit_rule_text(o))
    c.add("OUT-016")
    if rn and gdb:
        names = dataset_names(rn, o)
        c.add("OUT-011", names=", ".join(names))


def band_limits(o):
    """The eight per-band limits as floats / None (tolerates missing or malformed values)."""
    lb = o.get("limit_bands")
    out = []
    for i in range(8):
        v = lb[i] if isinstance(lb, (list, tuple)) and i < len(lb) else None
        out.append(float(v) if _finite(v) else None)
    return out


def limits_set(o):
    """True when at least one limit (overall dB(A) or any octave band) is defined."""
    return _finite(o.get("limit_dba")) or any(v is not None for v in band_limits(o))


def limit_rule_text(o):
    parts = []
    if _finite(o.get("limit_dba")):
        parts.append("LAeq <= %g dB(A)" % float(o["limit_dba"]))
    w = "dB(A)" if o.get("limit_band_weighting", "A") == "A" else "dB (unweighted)"
    for hz, v in zip(BANDS, band_limits(o)):
        if v is not None:
            parts.append("%d Hz <= %g %s" % (hz, v, w))
    return "; ".join(parts)


def dataset_names(run, o):
    names = []
    if o.get("overall_a"):
        names.append(run + "_LAeq")
    if o.get("overall_z"):
        names.append(run + "_LZ")
    for b in o.get("bands") or []:
        names.append("%s_Lp%s" % (run, b))
    if limits_set(o):
        names += [run + "_Margin", run + "_PassFail"]
    if o.get("detail") == "Full":
        names.append(run + "_Cells")
    names += [run + "_Summary", run + "_Snapshot"]
    return names


def _v_engine(c):
    try:
        py = config.find_python310()
    except NoiseBoxError as e:
        c.add("ENG-001", path=str(e)[:200])
        return
    if not os.path.isdir(config.core_dir()):
        c.add("ENG-003", path=config.core_dir())
    if not os.path.isfile(os.path.join(config.glue_dir(), "nb_job.m")):
        c.add("ENG-012", path=os.path.join(config.glue_dir(), "nb_job.m"))
    c.add("ENG-010")


# ------------------------------------------------------------------ DTM coverage (preview)
class DtmWindow:
    """The DTM resampled to the analysis CRS over a window; nearest-cell lookups that say why a point has no value."""

    def __init__(self, info, Z, factor=1.0):
        self.info, self.Z, self.f = info, Z, factor
        self.x0, self.y0, self.cs = info["x0"], info["y0"], info["cs"]
        self.nx, self.ny = info["nx"], info["ny"]

    def z(self, x, y):
        """-> (value in metres or None, reason 'ok'|'outside'|'nodata')."""
        ix = int(round((x - self.x0) / self.cs))
        iy = int(round((y - self.y0) / self.cs))
        if ix < 0 or iy < 0 or ix >= self.nx or iy >= self.ny:
            return None, "outside"
        v = self.Z[iy, ix]
        if v != v:
            return None, "nodata"
        return float(v) * self.f, "ok"


def load_dtm_window(sc, bbox, wkid, pad=100.0):
    """DTM window over bbox for coverage checks. -> DtmWindow (raises NoiseBoxError when the DTM has no overlap)."""
    from . import arcgis_io as aio
    import arcpy
    path = sc["terrain"]["dtm"]["path"]
    info = dtm_info(path)
    f, _, _ = dtm_unit_factor(sc, info)
    sr = arcpy.SpatialReference(int(wkid))
    try:
        dem, Z, _ = aio.dem_from_raster(path, sr, bbox, pad)
    except NoiseBoxError:
        raise
    except Exception as e:
        raise NoiseBoxError(I.make("DTM-012").message + " (%s)" % str(e)[:100])
    return DtmWindow(dem, Z, f or 1.0)


def coverage(sc, win, rings, sxy, n_paths=48, step=None):
    """Check DTM coverage of the receiver area and of paths from the source to it.

    -> dict(source_status, pct_area_missing, gaps [(x,y,reason)], n_paths_with_gaps)."""
    zs, why = win.z(*sxy)
    out = {"source_status": why, "source_ground": zs}
    bb = S.bbox_of([p for r in rings for p in r])
    step = step or max(win.cs, 1.0)
    n = 40
    miss = tot = 0
    gaps = []
    for i in range(n):
        for j in range(n):
            x = bb[0] + (i + 0.5) * (bb[2] - bb[0]) / n
            y = bb[1] + (j + 0.5) * (bb[3] - bb[1]) / n
            if any(S.point_in_ring(x, y, r) for r in rings):
                tot += 1
                v, why = win.z(x, y)
                if v is None:
                    miss += 1
                    if len(gaps) < 300:
                        gaps.append((x, y, why))
    out["pct_area_missing"] = 100.0 * miss / tot if tot else 0.0
    bnd = [p for r in rings for p in S.densify(r + [r[0]], max((bb[2] - bb[0] + bb[3] - bb[1]) / (n_paths / 2.0), step))]
    bnd = bnd[:: max(1, len(bnd) // n_paths)]
    bad = 0
    for p in bnd:
        hit = False
        for q in S.densify([sxy, p], step):
            v, why = win.z(*q)
            if v is None:
                hit = True
                if len(gaps) < 300:
                    gaps.append((q[0], q[1], why))
                break
        bad += hit
    out["n_paths_with_gaps"] = bad
    out["n_paths"] = len(bnd)
    out["gaps"] = gaps
    return out


def deep_dtm_checks(sc, wkid, dtm_issues=None):
    """Coverage-related issues for Preview/Run: needs arcpy and a DTM. -> (issues, coverage dict or None, DtmWindow)."""
    c = _Ctx(sc)
    rings, bb = area_rings(sc, wkid)
    if rings is None or not sc["terrain"].get("dtm") or not _finite(sc["source"].get("x")):
        return [], None, None
    sxy = source_xy(sc, wkid)
    pts = [sxy] + [p for r in rings for p in r]
    allbb = S.bbox_of(pts)
    for st in sc["structures"]:
        if st.get("include", True):
            for key in ("footprint", "path"):
                if st.get(key):
                    allbb = S.bbox_of([(allbb[0], allbb[1]), (allbb[2], allbb[3])] + _xf_ring(st, key, wkid))
    try:
        win = load_dtm_window(sc, allbb, wkid)
    except NoiseBoxError:
        c.add("DTM-012")
        return c.issues, None, None
    cov = coverage(sc, win, rings, sxy)
    if cov["source_status"] == "outside":
        c.add("DTM-008")
    elif cov["source_status"] == "nodata":
        c.add("DTM-009")
    if cov["pct_area_missing"] >= 99.5:
        c.add("DTM-012")
    elif cov["pct_area_missing"] > 0.5:
        c.add("DTM-010", pct=cov["pct_area_missing"])
    if cov["n_paths_with_gaps"]:
        c.add("DTM-011", n=cov["n_paths_with_gaps"])
    if cov["source_ground"] is not None:
        c.add("DTM-017", ground=cov["source_ground"])
        c.add("SRC-018", ground=cov["source_ground"], h=sc["source"].get("height_m") or 0.0,
              absolute=cov["source_ground"] + (sc["source"].get("height_m") or 0.0))
    for st in sc["structures"]:
        if st.get("type") == "barrier" and st.get("include", True):
            path = _barrier_path(st, wkid)
            if path and len(path) >= 2:
                vals = [win.z(x, y) for _, x, y in [(0, p[0], p[1]) for p in S.densify(path, win.cs)]]
                miss = [i for i, (v, _) in enumerate(vals) if v is None]
                if miss:
                    c.add("BAR-021", object_id=st.get("id", ""), name=st.get("name"), pct=100.0 * len(miss) / len(vals))
                v = st.get("vertical") or {}
                if v.get("mode") == "absolute" and _finite(v.get("value")):
                    zs = [z for z, _ in vals if z is not None]
                    if zs and v["value"] <= max(zs):
                        c.add("BAR-008", object_id=st.get("id", ""), name=st.get("name"), top=v["value"],
                              ground=max(zs), where="its highest ground point")
                    elif zs and v["value"] - max(zs) < 1.0:
                        c.add("BAR-009", object_id=st.get("id", ""), name=st.get("name"), clear=v["value"] - max(zs))
                elif v.get("mode") == "relative" and _finite(v.get("value")):
                    zs = [z for z, _ in vals if z is not None]
                    if zs and max(zs) - min(zs) > 1.0:
                        c.add("BAR-010", object_id=st.get("id", ""), name=st.get("name"), top=max(zs) + v["value"],
                              h=v["value"])
    return c.issues, cov, win


def _barrier_path(st, wkid):
    pl = st.get("placement") or {}
    if pl.get("mode") == "straight" and pl.get("start") and _finite(pl.get("length_m")) and _finite(pl.get("azimuth_deg")):
        iw = st.get("input_wkid") or wkid
        sx, sy = transform_xy(pl["start"][0], pl["start"][1], iw, wkid)
        return S.barrier_from_placement((sx, sy), pl["length_m"], pl["azimuth_deg"])
    if st.get("path"):
        return S.clean_path(_xf_ring({"input_wkid": st.get("input_wkid"), "p": st["path"]}, "p", wkid))
    return None


def barrier_profile(sc, barrier_id, win=None, step=None):
    """Ground and barrier top along a barrier, for the profile preview. -> [(s, ground, top)] (None where unknown)."""
    wkid = analysis_wkid(sc)
    st = next(s for s in sc["structures"] if s.get("id") == barrier_id)
    path = _barrier_path(st, wkid)
    v = st["vertical"]
    if win is None:
        sample = lambda x, y: (0.0, "ok")
    else:
        sample = win.z
    pts = S.profile_along(path, lambda x, y: sample(x, y)[0], step or (win.cs if win else 5.0))
    zs = [p[3] for p in pts if p[3] is not None]
    flat_top = (max(zs) + v["value"]) if (v["mode"] == "relative" and zs) else v["value"]
    return [(s, z, (flat_top if v["mode"] == "relative" else v["value"])) for s, x, y, z in pts], flat_top


def section_summaries(sc):
    """One line per pane section, as shown when the section is collapsed."""
    s = sc["source"]
    src = ("%s, %s m above ground" % (s.get("name") or "Source", _fmt(s.get("height_m")))
           if _finite(s.get("height_m")) and s.get("x") is not None else "Not set")
    t = sc["terrain"]
    a = sc["area"]
    dtm = (t["dtm"].get("name") or os.path.basename(t["dtm"]["path"])) if t.get("dtm") else "Flat ground"
    c = a["cell"]
    cell = ("match DTM" if c.get("mode") == "match_dtm" else "%s m output cells" % _fmt(c.get("size_m"))) if (
        c.get("mode") == "match_dtm" or c.get("size_m")) else "cell size not set"
    sts = sc.get("structures", [])
    nb = sum(1 for x in sts if x["type"] == "building")
    nbar_act = sum(1 for x in sts if x["type"] == "barrier" and x.get("include", True))
    nenc = sum(1 for x in sts if x["type"] == "enclosure")
    parts = []
    if nb:
        parts.append("%d building%s" % (nb, "" if nb == 1 else "s"))
    if nbar_act or any(x["type"] == "barrier" for x in sts):
        parts.append("%d active barrier%s" % (nbar_act, "" if nbar_act == 1 else "s"))
    if nenc:
        parts.append("%d enclosure%s" % (nenc, "" if nenc == 1 else "s"))
    p = sc["propagation"]
    g = p["ground"]
    gtxt = "G = %s" % _fmt(g["G"]) if not g.get("separate") else "G %s/%s/%s" % (_fmt(g["Gs"]), _fmt(g["Gm"]), _fmt(g["Gr"]))
    return {"source": src, "terrain": "%s, %s" % (dtm, cell), "structures": ", ".join(parts) or "None",
            "propagation": "%s, %s, %s C, %s %% RH, %s" % (p["mode"], gtxt, _fmt(p["atmosphere"]["T_C"]),
                                                          _fmt(p["atmosphere"]["RH"]),
                                                          "long-term" if p["meteorology"]["method"] == "long_term" else "favourable"),
            "outputs": (sc["outputs"].get("run_name") or "run name not set") + (
                ", limits: " + limit_rule_text(sc["outputs"]) if limits_set(sc["outputs"]) else "")}


def _fmt(v):
    if v is None:
        return "?"
    return ("%g" % v) if isinstance(v, (int, float)) else str(v)
