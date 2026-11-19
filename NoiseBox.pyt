# -*- coding: utf-8 -*-
"""NoiseBox: ISO 9613-2 noise maps in ArcGIS Pro. Thin wrapper: all physics runs in matlab/core/*.m.

Keep this file light: no module-level side effects (the toolbox is loaded on every refresh).
Tool dialogs are split into numbered sections (parameter categories):
  1 Sources | 2 Barriers & terrain | 3 Ground & atmosphere | 4 Calculation area / Receivers
  5 Limits (optional) | 6 Outputs
Every input can be picked from a list of layers in the map OR drawn on the spot (feature-set parameters).
"""
import importlib
import os
import sys

import arcpy

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

BANDS = (63, 125, 250, 500, 1000, 2000, 4000, 8000)
MODES = ["iso2024", "draft2026", "iso1996"]
DETAIL = ["Full", "Levels only", "None"]
WEIGHTING = {"Unweighted band level Lp": "Z", "A-weighted band level LpA": "A"}
S1, S2, S3 = "1. Sources", "2. Barriers & terrain", "3. Ground & atmosphere"
S4A, S4R = "4. Calculation area", "4. Receivers"
S5, S6 = "5. Limits (optional)", "6. Outputs"


def _nb():
    """Import the helper package fresh, so edits to noisebox/*.py apply after a toolbox Refresh."""
    from noisebox import (config, issues, structures, scenario, arcgis_io, exchange, outputs, pipeline,
                          scenario_run)
    for m in (config, issues, structures, scenario, arcgis_io, exchange, outputs, pipeline, scenario_run):
        importlib.reload(m)
    return pipeline, arcgis_io


class _ToolLog:
    def __init__(self):
        self._stepped = False

    def msg(self, s):
        arcpy.AddMessage(s)

    def warn(self, s):
        arcpy.AddWarning(s)

    def progress(self, done, total, text):
        try:
            if total and not self._stepped:
                arcpy.SetProgressor("step", text, 0, int(total), 1)
                self._stepped = True
            if self._stepped:
                arcpy.SetProgressorPosition(int(done))
            arcpy.SetProgressorLabel(text)
        except Exception:
            pass

    def cancelled(self):
        return arcpy.env.isCancelled


def _run(fn, *args):
    """Run a pipeline function; user-facing NoiseBoxError becomes one clean tool error (no chained traceback)."""
    err = None
    arcpy.SetProgressor("default", "Starting MATLAB (10-80 s) ...")
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001
        if not any(c.__name__ == "NoiseBoxError" for c in type(e).__mro__):   # includes IssuesError
            raise
        err = str(e)
    finally:
        arcpy.ResetProgressor()
    raise arcpy.ExecuteError(err)


def _P(name, label, dtype, cat=None, ptype="Optional", direction="Input", default=None, filt=None, deps=None):
    p = arcpy.Parameter(displayName=label, name=name, datatype=dtype, parameterType=ptype, direction=direction)
    if default is not None:
        p.value = default
    if filt is not None:
        p.filter.type = "ValueList"
        p.filter.list = list(filt)
    if deps:
        p.parameterDependencies = deps
    if cat:
        p.category = cat
    return p


def _by_name(parameters):
    return {p.name: p for p in parameters}


# ------------------------------------------------------------------ parameter groups
def _templates():
    try:
        _, aio = _nb()
        return aio.ensure_templates()
    except Exception:
        return {}


def _draw(name, label, cat, template):
    p = _P(name, label, "GPFeatureRecordSetLayer", cat)
    if template:
        p.value = template
    return p


def _sources_params(t, with_defaults=True):
    ps = [
        _P("sources", "Source points (pick from the map)", "GPFeatureLayer", S1),
        _draw("sources_draw", "...or draw source points on the map", S1, t.get("sources")),
        _P("h_field", "Height field of picked sources (m above ground)", "Field", S1, deps=["sources"]),
        _P("lw_prefix", "Lw field prefix of picked sources (<prefix>63 ... <prefix>8000, dB re 1 pW)", "GPString",
           S1, default="Lw_"),
        _P("def_h", "Default height for drawn sources (m)", "GPDouble", S1, default=1.0),
        _P("def_lw", "Default Lw for drawn sources (8 octave bands 63-8000 Hz, dB, comma-separated)", "GPString", S1,
           default="100,100,100,100,100,95,90,85"),
    ]
    return ps


def _terrain_params(t):
    return [
        _P("barriers", "Barrier / building polygons (pick from the map)", "GPFeatureLayer", S2),
        _draw("barriers_draw", "...or draw barriers / buildings on the map", S2, t.get("barriers")),
        _P("b_field", "Height field of picked barriers (m above ground)", "Field", S2, deps=["barriers"]),
        _P("def_bh", "Default height for drawn barriers (m)", "GPDouble", S2, default=4.0),
        _P("dem", "Elevation raster (DEM, metres; flat ground if empty)", "GPRasterLayer", S2),
    ]


def _physics_params():
    return [
        _P("G", "Ground factor G (0 hard ... 1 porous)", "GPDouble", S3, default=0.5),
        _P("hr", "Receiver height (m above ground)", "GPDouble", S3, default=1.5),
        _P("T", "Temperature (deg C)", "GPDouble", S3, default=15.0),
        _P("RH", "Relative humidity (%)", "GPDouble", S3, default=70.0),
        _P("mode", "Formula mode", "GPString", S3, default="iso2024", filt=MODES),
    ]


def _limit_params():
    ps = [
        _P("overall", "Allowed overall level (dB(A)); empty = none", "GPDouble", S5, default=55.0),
        _P("weighting", "Band limits compare with", "GPString", S5, default="Unweighted band level Lp",
           filt=WEIGHTING.keys()),
    ]
    for b in BANDS:
        ps.append(_P("lim%d" % b, "Allowed level in the %d Hz band (dB); empty = none" % b, "GPDouble", S5))
    return ps


def _output_params(map_default=True, with_raster_options=True):
    ps = [
        _P("out_gdb", "Output geodatabase", "DEWorkspace", S6, ptype="Required"),
        _P("run_name", "Run name (prefix of every output; made unique automatically)", "GPString", S6,
           default="NoiseRun"),
    ]
    if with_raster_options:
        ps += [
            _P("iso_step", "Noise-band polygons: class width (dB(A)); 0 = none", "GPDouble", S6, default=5.0),
            _P("bands", "Also write one raster per octave band (unweighted Lp)", "GPBoolean", S6, default=False),
        ]
    ps += [_P("detail", "Click-to-inspect detail cells (all levels and attenuations)", "GPString", S6,
              default="Full", filt=DETAIL)]
    if with_raster_options:
        ps += [_P("copy_inputs", "Save a copy of the inputs used", "GPBoolean", S6, default=True)]
    ps += [_P("add_map", "Add results to the active map (in groups)", "GPBoolean", S6, default=map_default)]
    return ps


# ------------------------------------------------------------------ shared validation / defaults
def _map_defaults(P):
    """Pre-fill empty inputs from the active map (first layer whose name fits) and the project gdb."""
    try:
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        m = aprx.activeMap
    except Exception:
        return
    if "out_gdb" in P and not P["out_gdb"].altered and not P["out_gdb"].value:
        try:
            P["out_gdb"].value = aprx.defaultGeodatabase
        except Exception:
            pass
    if m is None:
        return
    rules = (("sources", ("source",), "point"), ("barriers", ("barrier", "building", "wall"), "polygon"),
             ("area", ("area", "study", "boundary", "extent"), "polygon"), ("receivers", ("receiver",), "point"),
             ("dem", ("dem", "elev", "srtm", "dtm", "terrain"), "raster"))
    for pname, keys, kind in rules:
        if pname not in P or P[pname].altered or P[pname].value:
            continue
        for lyr in m.listLayers():
            try:
                if lyr.isGroupLayer or not any(k in lyr.name.lower() for k in keys):
                    continue
                if kind == "raster" and lyr.isRasterLayer:
                    P[pname].value = lyr
                    break
                if kind != "raster" and lyr.isFeatureLayer:
                    st = arcpy.Describe(lyr).shapeType.lower()
                    if st == kind:
                        P[pname].value = lyr
                        break
            except Exception:
                continue


def _autofield(P, layer, field, cands):
    if layer in P and field in P and P[layer].value and not P[field].altered and not P[field].value:
        try:
            names = [f.name for f in arcpy.ListFields(P[layer].value)]
        except Exception:
            return
        for cand in cands:
            for n in names:
                if n.lower() == cand:
                    P[field].value = n
                    return


def _update(parameters):
    P = _by_name(parameters)
    _map_defaults(P)
    for f in ("h_field", "b_field", "rh_field"):
        if f in P:
            P[f].filter.list = ["Short", "Long", "Float", "Double"]
    _autofield(P, "sources", "h_field", ("h_src", "height", "h"))
    _autofield(P, "barriers", "b_field", ("h_bar", "height", "h"))
    _autofield(P, "receivers", "rh_field", ("h_rec",))
    # drawn-feature defaults only matter when something is drawn; picked-layer fields only when a layer is picked
    return P


def _check_layer(P, name, what, geom=None):
    if name in P and P[name].value:
        try:
            d = arcpy.Describe(P[name].value)
            sr = d.spatialReference
            if sr is None or sr.type != "Projected":
                P[name].setErrorMessage("%s must use a projected CRS in metres, not a geographic one (degrees). "
                                        "Project it first." % what)
            elif abs(sr.metersPerUnit - 1.0) > 1e-9:
                P[name].setErrorMessage("%s: CRS units must be metres (found %s)." % (what, sr.linearUnitName))
            if geom and d.shapeType != geom:
                P[name].setErrorMessage("%s must be a %s feature class." % (what, geom.lower()))
        except Exception:
            pass


def _messages(parameters):
    P = _by_name(parameters)
    _check_layer(P, "sources", "Source points", "Point")
    _check_layer(P, "barriers", "Barrier polygons", "Polygon")
    _check_layer(P, "area", "Calculation-area polygon", "Polygon")
    _check_layer(P, "receivers", "Receivers", "Point")
    if "sources" in P and not P["sources"].value and not P["sources_draw"].value:
        P["sources"].setWarningMessage("Pick a source layer, or draw source points below.")
    if P.get("sources") is not None and P["sources"].value and not P["h_field"].value:
        P["h_field"].setErrorMessage("Choose the source height field.")
    if "barriers" in P and P["barriers"].value and not P["b_field"].value:
        P["b_field"].setErrorMessage("Choose the barrier height field.")
    for name, lo, hi, msg in (("G", 0, 1, "G must be between 0 and 1."),
                              ("RH", 0, 100, "Relative humidity must be 0-100 %.")):
        v = P[name].value
        if v is not None and not (lo <= v <= hi):
            P[name].setErrorMessage(msg)
    if P["hr"].value is not None and P["hr"].value <= 0:
        P["hr"].setErrorMessage("Receiver height must be > 0.")
    if "cell" in P and P["cell"].value is not None and P["cell"].value <= 0:
        P["cell"].setErrorMessage("Cell size must be > 0.")
    if "def_lw" in P and P["def_lw"].value:
        try:
            _, aio = _nb()
            aio.parse_lw(P["def_lw"].value)
        except Exception as e:
            P["def_lw"].setErrorMessage(str(e))


def _scene_dict(P):
    def v(n):
        return P[n].valueAsText if n in P and P[n].value is not None else None

    def num(n):
        return P[n].value if n in P else None
    d = {
        "sources": v("sources"), "sources_draw": v("sources_draw"), "h_field": v("h_field"),
        "lw_prefix": v("lw_prefix") or "Lw_", "def_h": num("def_h"), "def_lw": v("def_lw"),
        "barriers": v("barriers"), "barriers_draw": v("barriers_draw"), "b_field": v("b_field"),
        "def_bh": num("def_bh"), "dem": v("dem"),
        "G": num("G"), "hr": num("hr"), "T": num("T"), "RH": num("RH"), "mode": v("mode") or "iso2024",
        "overall": num("overall"), "weighting": WEIGHTING.get(v("weighting"), "Z"),
        "band_limits": [num("lim%d" % b) for b in BANDS],
        "out_gdb": v("out_gdb"), "run_name": v("run_name"), "detail": v("detail") or "Full",
        "add_map": bool(P["add_map"].value) if "add_map" in P else True,
    }
    return d


# ------------------------------------------------------------------ toolbox
class Toolbox:
    def __init__(self):
        self.label = "NoiseBox"
        self.alias = "noisebox"
        self.tools = [CreateInputLayers, NoiseMap, NoiseAtReceivers, CompareNoiseMaps, CheckMatlabLink, RunScenario]


class CreateInputLayers:
    def __init__(self):
        self.label = "Create Input Layers"
        self.description = ("Creates empty Sources, Barriers, Receivers and Calculation-area layers with the "
                            "NoiseBox fields (h_src, Lw_63 ... Lw_8000, h_bar, h_rec) in a geodatabase and adds them "
                            "to the map, ready to draw or edit.")
        self.category = "1. Prepare"

    def getParameterInfo(self):
        return [
            _P("out_gdb", "Output geodatabase", "DEWorkspace", ptype="Required"),
            _P("prefix", "Layer name prefix", "GPString", default="NB_"),
            _P("sr", "Coordinate system (projected, metres)", "GPSpatialReference"),
            _P("add_map", "Add the layers to the active map", "GPBoolean", default=True),
        ]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        P = _by_name(parameters)
        _map_defaults(P)
        if not P["sr"].altered and not P["sr"].value:
            try:
                _, aio = _nb()
                P["sr"].value = aio.default_template_sr()
            except Exception:
                pass

    def updateMessages(self, parameters):
        P = _by_name(parameters)
        sr = P["sr"].value
        if sr is not None:
            try:
                if sr.type != "Projected" or abs(sr.metersPerUnit - 1.0) > 1e-9:
                    P["sr"].setErrorMessage("Choose a projected coordinate system in metres.")
            except Exception:
                pass

    def execute(self, parameters, messages):
        pipeline, _ = _nb()
        P = _by_name(parameters)
        p = {"out_gdb": P["out_gdb"].valueAsText, "prefix": P["prefix"].valueAsText, "sr": P["sr"].value,
             "add_map": bool(P["add_map"].value)}
        _run(pipeline.create_input_layers, p, _ToolLog())

    def postExecute(self, parameters):
        return


class NoiseMap:
    def __init__(self):
        self.label = "Noise Map (LAeq raster)"
        self.description = ("ISO 9613-2 LAeq dB(A) raster from point sources, with optional barriers/buildings, a DEM, "
                            "allowed levels, noise bands, per-octave-band rasters and click-to-inspect detail cells. "
                            "Results are added to the map in one group per run. Physics: MATLAB core matlab/core.")
        self.category = "2. Calculate"

    def getParameterInfo(self):
        t = _templates()
        ps = _sources_params(t) + _terrain_params(t) + _physics_params()
        ps += [
            _P("area", "Calculation-area polygon (pick from the map)", "GPFeatureLayer", S4A),
            _draw("area_draw", "...or draw the calculation area on the map", S4A, t.get("area")),
            _P("extent", "...or an extent (rectangle)", "GPExtent", S4A),
            _P("clip", "Leave cells outside a polygon empty", "GPBoolean", S4A, default=True),
            _P("cell", "Cell size (m); empty = automatic (about 150 cells across)", "GPDouble", S4A),
        ]
        ps += _limit_params() + _output_params()
        return ps

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        _update(parameters)

    def updateMessages(self, parameters):
        _messages(parameters)

    def execute(self, parameters, messages):
        pipeline, _ = _nb()
        P = _by_name(parameters)
        p = _scene_dict(P)
        p.update({"area": P["area"].valueAsText, "area_draw": P["area_draw"].valueAsText, "extent": P["extent"].value,
                  "clip": bool(P["clip"].value), "cell": P["cell"].value, "iso_step": P["iso_step"].value,
                  "bands": bool(P["bands"].value), "copy_inputs": bool(P["copy_inputs"].value)})
        created = _run(pipeline.sources_to_raster, p, _ToolLog())
        for k, v in created.items():
            arcpy.AddMessage("Created %s: %s" % (k, v))

    def postExecute(self, parameters):
        return


class NoiseAtReceivers:
    def __init__(self):
        self.label = "Noise at Receivers (points)"
        self.description = ("Levels at receiver points (picked or drawn): LAeq, every octave band, allowed-level "
                            "check and the attenuations per band, written as fields on a copy of the receivers.")
        self.category = "2. Calculate"

    def getParameterInfo(self):
        t = _templates()
        ps = _sources_params(t) + _terrain_params(t) + _physics_params()
        ps += [
            _P("receivers", "Receiver points (pick from the map)", "GPFeatureLayer", S4R),
            _draw("receivers_draw", "...or draw receiver points on the map", S4R, t.get("receivers")),
            _P("rh_field", "Height field of picked receivers (m); empty = height in section 3", "Field", S4R,
               deps=["receivers"]),
        ]
        ps += _limit_params() + _output_params(with_raster_options=False)
        return ps

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        _update(parameters)

    def updateMessages(self, parameters):
        _messages(parameters)

    def execute(self, parameters, messages):
        pipeline, _ = _nb()
        P = _by_name(parameters)
        p = _scene_dict(P)
        p.update({"receivers": P["receivers"].valueAsText, "receivers_draw": P["receivers_draw"].valueAsText,
                  "rh_field": P["rh_field"].valueAsText if P["rh_field"].value else None})
        _run(pipeline.points_to_fields, p, _ToolLog())

    def postExecute(self, parameters):
        return


class CompareNoiseMaps:
    def __init__(self):
        self.label = "Compare Noise Maps (scenario minus baseline)"
        self.description = ("Difference of two noise rasters computed on the same grid, e.g. with and without a "
                            "barrier. Negative = quieter in the scenario.")
        self.category = "3. Evaluate"

    def getParameterInfo(self):
        return [
            _P("baseline", "Baseline noise raster", "GPRasterLayer", "1. Rasters", ptype="Required"),
            _P("scenario", "Scenario noise raster", "GPRasterLayer", "1. Rasters", ptype="Required"),
            _P("threshold", "Report cells changed by at least (dB)", "GPDouble", "1. Rasters", default=3.0),
            _P("out_gdb", "Output geodatabase", "DEWorkspace", "2. Outputs", ptype="Required"),
            _P("run_name", "Run name", "GPString", "2. Outputs", default="Compare"),
            _P("add_map", "Add the result to the active map", "GPBoolean", "2. Outputs", default=True),
        ]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        _map_defaults(_by_name(parameters))

    def execute(self, parameters, messages):
        pipeline, _ = _nb()
        P = _by_name(parameters)
        p = {"baseline": P["baseline"].valueAsText, "scenario": P["scenario"].valueAsText,
             "threshold": P["threshold"].value, "out_gdb": P["out_gdb"].valueAsText,
             "run_name": P["run_name"].valueAsText, "add_map": bool(P["add_map"].value)}
        _run(pipeline.compare_rasters, p, _ToolLog())

    def postExecute(self, parameters):
        return


class RunScenario:
    """Runs one scenario file written by the NoiseBox add-in. In Pro it runs in-process, so the results are added to
    the open map (grouped, styled). The add-in validates first and shows every issue; this tool repeats the checks."""

    def __init__(self):
        self.label = "Run Scenario (used by the add-in)"
        self.description = ("Calculates a NoiseBox scenario saved by the NoiseBox ribbon tab (JSON file). "
                            "Use the ribbon for editing; use this tool for batch runs and scripts.")
        self.category = "5. Add-in"

    def getParameterInfo(self):
        p = _P("scenario", "Scenario file (.json)", "DEFile", ptype="Required")
        p.filter.list = ["json"]
        return [p]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        _nb()
        from noisebox import scenario, scenario_run
        sc, iss = scenario.load(parameters[0].valueAsText)
        if sc is None:
            raise arcpy.ExecuteError("; ".join(str(i) for i in iss))
        res = _run(scenario_run.run, sc, _ToolLog())
        arcpy.AddMessage("Created: " + ", ".join("%s=%s" % kv for kv in res["created"].items()))

    def postExecute(self, parameters):
        return


class CheckMatlabLink:
    def __init__(self):
        self.label = "Check MATLAB Link"
        self.description = "Checks the Python 3.10 environment, the MATLAB Engine, the .m file hashes and the solver."
        self.category = "4. Utilities"

    def getParameterInfo(self):
        return []

    def isLicensed(self):
        return True

    def execute(self, parameters, messages):
        pipeline, _ = _nb()
        ok = _run(pipeline.check_link, _ToolLog())
        if not ok:
            arcpy.AddWarning("MATLAB link works but the checks above reported a problem.")
        else:
            arcpy.AddMessage("MATLAB link OK.")

    def postExecute(self, parameters):
        return
