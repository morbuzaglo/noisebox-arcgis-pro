"""Scenario builders shared by the scenario tests (propy)."""
import copy
import os

from common import *  # noqa: F401,F403
from noisebox import scenario as SC

BAND_LW = [100.0, 100.0, 100.0, 100.0, 100.0, 95.0, 90.0, 85.0]
MASS_LAW = lambda m: {"mode": "mass_law", "surface_mass_kg_m2": m, "thickness_m": None, "volume_density_kg_m3": None,
                      "solid": True, "tl_model": "normal", "TL": None, "alpha": [0.3] * 8}
MANUF = lambda tl, al: {"mode": "manufacturer", "surface_mass_kg_m2": None, "thickness_m": None,
                        "volume_density_kg_m3": None, "solid": True, "tl_model": "normal", "TL": tl, "alpha": al}


def base_scenario(gdb=None, run="r", dtm=None, cell=10.0):
    """Valid scenario on the sample site (ITM): 1 source, 100 x 60 m receiver rectangle, flat ground, nothing else."""
    sc = SC.new_scenario("Test scenario", wkid=2039)
    sc["source"].update(SC.source_from_coords(X0, Y0, 2039))
    sc["source"]["height_m"] = 1.0
    sc["source"]["spectrum"]["lw"] = list(BAND_LW)
    sc["area"].update({"mode": "extent", "extent": [X0 + 30, Y0 - 30, X0 + 130, Y0 + 30], "input_wkid": 2039})
    sc["area"]["cell"] = {"mode": "custom", "size_m": cell}
    sc["outputs"].update({"gdb": gdb or os.path.join(ROOT, "sample", "NoiseBox_sample.gdb"), "run_name": run,
                          "add_to_map": False, "overall_a": True})
    if dtm:
        sc["terrain"]["dtm"] = {"path": dtm, "name": os.path.basename(dtm)}
        sc["terrain"]["vertical_unit"] = "m"
    return sc


def building(name="Wall bld", ring=None, h=4.0, include=True, visible=True, sid="b1"):
    ring = ring or [(X0 + 20, Y0 - 100), (X0 + 20, Y0 + 100), (X0 + 20.5, Y0 + 100), (X0 + 20.5, Y0 - 100)]
    return {"id": sid, "type": "building", "name": name, "include": include, "visible": visible,
            "footprint": [list(p) for p in ring], "input_wkid": 2039, "height_m": h,
            "height_source": {"mode": "single"}, "layer": None}


def barrier(name="Screen", path=None, h=4.0, include=True, visible=True, sid="w1", mode="relative", transmission=None):
    path = path or [(X0 + 20, Y0 - 100), (X0 + 20, Y0 + 100)]
    return {"id": sid, "type": "barrier", "name": name, "include": include, "visible": visible,
            "path": [list(p) for p in path], "input_wkid": 2039, "placement": {"mode": "drawn"},
            "vertical": {"mode": mode, "value": h}, "gap_m": 0.0,
            "transmission": transmission or {"enabled": False, "material": None}}


def enclosure(name="Enclosure", material=None, h=3.0, include=True, visible=True, sid="e1", length=6.0, width=4.0):
    return {"id": sid, "type": "enclosure", "name": name, "include": include, "visible": visible,
            "source_link": "source", "mode": "rectangle",
            "rect": {"length_m": length, "width_m": width, "orientation_deg": 0.0, "offset": [0.0, 0.0]},
            "footprint": None, "height_m": h, "open_area_m2": 0.0,
            "faces": {"mode": "single", "all": material or MASS_LAW(25.0), "faces": {}}}


def codes(sc, deep=False):
    return {i.code for i in SC.validate(sc, deep=deep)}


def mutated(**changes):
    """base_scenario with dotted-path changes, e.g. mutated(**{"source.height_m": None})."""
    sc = base_scenario()
    for k, v in changes.items():
        d = sc
        parts = k.split(".")
        for p in parts[:-1]:
            d = d[p]
        d[parts[-1]] = copy.deepcopy(v)
    return sc
