"""Scenario tests that need no MATLAB (propy): catalogue integrity, source location methods, spectrum input, geometry,
and the validation rules. Usage: propy tests\\test_scenario.py <outdir>"""
import copy
import os
import re
import sys

from common import *  # noqa: F401,F403
from scn_common import *  # noqa: F401,F403
from noisebox import issues as I, scenario as SC, structures as S
from noisebox.config import NoiseBoxError

RESULTS = []
SEEN = set()


def report(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("RESULT %-62s %s %s" % (name, "PASS" if ok else "FAIL", detail))


def expect(name, sc, want, deep=False, absent=()):
    got = {i.code for i in SC.validate(sc, deep=deep)}
    SEEN.update(got)
    ok = set(want) <= got and not (set(absent) & got)
    report(name, ok, "" if ok else "wanted %s, unwanted %s, got %s" % (sorted(want), sorted(absent), sorted(got)))


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "tests", "out")
    gdb = fresh_gdb(outdir, "scn")

    print("=== 1. Catalogue integrity ===")
    cat = I.CATALOGUE
    report("at least 250 distinct codes", len(cat) >= 250, "%d codes" % len(cat))
    bad_fmt = []
    for code, (sev, sec, msg, fix) in cat.items():
        if sev not in (I.ERROR, I.WARNING, I.INFO) or sec not in ("scenario", "source", "terrain", "area", "structures",
                                                                  "propagation", "outputs", "engine"):
            bad_fmt.append(code)
        if sev == I.ERROR and not fix:
            bad_fmt.append(code + " (error without a fix)")
        try:
            i = I.make(code, name="x", value=1, bands="63")
            if not i.message:
                bad_fmt.append(code)
        except Exception as e:  # noqa: BLE001
            bad_fmt.append("%s: %s" % (code, e))
    report("every entry has a valid severity, section, message, and errors say how to fix", not bad_fmt, str(bad_fmt[:5]))
    used = set()
    for f in ("scenario.py", "scenario_run.py", "cli.py"):
        with open(os.path.join(ROOT, "noisebox", f), "r", encoding="utf-8") as fh:
            used |= set(re.findall(r'"([A-Z]{3}-\d{3})"', fh.read()))
    missing = sorted(c for c in used if c not in cat)
    report("every code used in the code exists in the catalogue", not missing, str(missing))

    print("\n=== 2. The three ways to define the source give the same input ===")
    sc_pt = {"x": X0, "y": Y0}
    a = SC.source_from_coords(X0, Y0, 2039)
    b = SC.source_from_map(X0, Y0, 2039)
    # layer: the sample gdb source, by OID key
    c, oids = SC.source_from_layer(os.path.join(GDB, "sources"), "key", 1, None)
    # coordinates typed in WGS 84 for the same physical point
    import arcpy
    g = arcpy.PointGeometry(arcpy.Point(X0, Y0), arcpy.SpatialReference(2039)).projectAs(arcpy.SpatialReference(4326))
    d = SC.source_from_coords(g.firstPoint.X, g.firstPoint.Y, 4326)
    e = SC.source_from_map(g.firstPoint.X, g.firstPoint.Y, 4326)       # map in WGS 84 (e.g. Web Mercator-less basemap)
    pts = []
    for nm, src in (("coords ITM", a), ("map click ITM", b), ("from layer", c), ("coords WGS84", d), ("map WGS84", e)):
        s = SC.new_scenario("t", wkid=2039)
        s["source"].update(src)
        pts.append((nm,) + SC.source_xy(s, 2039))
    spread = max(max(abs(p[1] - X0), abs(p[2] - Y0)) for p in pts)
    report("same physical point -> same analysis coordinates (< 1 mm)", spread < 1e-3,
           "max deviation %.2e m" % spread)
    sc2 = base_scenario()
    sc2["source"].update(d)
    sc2["crs"]["wkid"] = None
    report("WGS 84 entry with no analysis CRS picks Israeli TM Grid", SC.analysis_wkid(sc2) == 2039)
    lab = SC.coordinate_labels(2039)
    lab2 = SC.coordinate_labels(4326)
    report("coordinate labels follow the CRS", lab["label_x"] == "Easting" and lab["label_y"] == "Northing"
           and lab2["label_x"] == "Longitude" and lab2["label_y"] == "Latitude",
           "%s | %s" % (lab["order"], lab2["order"]))
    report("UTM suggestion for a non-Israeli site", SC.suggest_projected(10.0, 50.0) == 32632
           and SC.suggest_projected(-70, -33) == 32719)

    print("\n=== 3. Spectrum input ===")
    v, _ = SC.parse_spectrum_text("90\t91\t92\t93\t94\t95\t96\t97")
    report("pasted row (tab separated)", v == [90, 91, 92, 93, 94, 95, 96, 97])
    v, _ = SC.parse_spectrum_text("90\n91\n92\n93\n94\n95\n96\n97\n")
    report("pasted column", v == [90, 91, 92, 93, 94, 95, 96, 97])
    v, _ = SC.parse_spectrum_text("63;80\n125;81\n250;82\n500;83\n1000;84\n2000;85\n4000;86\n8000;87")
    report("two columns frequency;level", v == [80, 81, 82, 83, 84, 85, 86, 87])
    v, _ = SC.parse_spectrum_text("63,125,250,500,1000,2000,4000,8000\n70,71,72,73,74,75,76,77")
    report("two rows: frequencies then levels", v == [70, 71, 72, 73, 74, 75, 76, 77])
    v, iss = SC.parse_spectrum_text("90,5\t91\t92\t93\t94\t95\t96\t97")
    report("comma decimal read with a warning", v[0] == 90.5 and any(i.code == "SPC-014" for i in iss))
    v, iss = SC.parse_spectrum_text("90\t\t92\t93\t94\t95\t96\t97")
    report("empty cell stays missing (None), not 0", v[1] is None)
    v, iss = SC.parse_spectrum_text("1\t2\t3")
    report("wrong count is rejected with SPC-008", v is None and any(i.code == "SPC-008" for i in iss))
    v, iss = SC.parse_spectrum_text("63;80\n100;81\n")
    report("unsupported frequency is rejected with SPC-010", v is None and any(i.code == "SPC-010" for i in iss))
    csvp = os.path.join(outdir, "spec.csv")
    with open(csvp, "w", encoding="utf-8") as f:
        f.write("f,Lw\n63,80\n125,81\n250,82\n500,83\n1000,84\n2000,85\n4000,86\n8000,87\n")
    v, iss = SC.read_spectrum_csv(csvp)
    report("CSV with header", v == [80, 81, 82, 83, 84, 85, 86, 87])
    v, iss = SC.read_spectrum_csv(os.path.join(outdir, "nope.csv"))
    report("missing CSV -> SPC-009", v is None and iss[0].code == "SPC-009")
    os.environ["NOISEBOX_PROFILE_DIR"] = os.path.join(outdir, "profiles")
    SC.save_profile("Drill-01 test", BAND_LW)
    report("save / load / list a named profile", SC.load_profile("Drill-01 test")["lw"] == BAND_LW
           and "Drill-01 test" in SC.list_profiles())

    print("\n=== 4. Geometry helpers ===")
    st = S.barrier_from_placement((0, 0), 100.0, 90.0)
    report("barrier azimuth 90 deg points east", abs(st[1][0] - 100) < 1e-9 and abs(st[1][1]) < 1e-9)
    st = S.barrier_from_placement((0, 0), 10.0, 0.0)
    report("barrier azimuth 0 deg points north", abs(st[1][0]) < 1e-9 and abs(st[1][1] - 10) < 1e-9)
    r = S.rect_footprint((0, 0), 6.0, 4.0, 0.0)
    report("rectangle: length along the orientation (north), area 24 m2", abs(S.ring_area(r) - 24) < 1e-9
           and abs(max(p[1] for p in r) - 3.0) < 1e-9)
    f = S.enclosure_faces(r, 3.0)
    names = [x["name"] for x in f]
    report("enclosure faces: 4 walls named by facing + roof; areas", len(f) == 5 and names[-1] == "Roof"
           and abs(sum(x["area"] for x in f) - (2 * (6 + 4) * 3 + 24)) < 1e-9, ", ".join(names))
    report("self intersection found in a bow tie", S.self_intersection([(0, 0), (2, 2), (2, 0), (0, 2)]) is not None
           and S.self_intersection([(0, 0), (2, 0), (2, 2), (0, 2)]) is None)

    print("\n=== 5. Validation rules (each case checks that the right message appears) ===")
    expect("valid base scenario has no error", base_scenario(), [], absent=[c for c, v in I.CATALOGUE.items() if v[0] == I.ERROR])
    # scenario / CRS
    expect("no scenario name", mutated(name=""), ["SCN-004"])
    expect("no CRS and a source without a CRS", mutated(**{"crs.wkid": None, "source.input_wkid": None}), ["SCN-006"])
    expect("geographic analysis CRS", mutated(**{"crs.wkid": 4326}), ["SCN-007"])
    expect("unknown CRS code", mutated(**{"crs.wkid": 99999}), ["SCN-009"])
    expect("CRS in feet", mutated(**{"crs.wkid": 2227}), ["SCN-008"])
    # source
    expect("no source", mutated(**{"source.x": None, "source.y": None}), ["SRC-001"])
    expect("source x not a number", mutated(**{"source.x": "abc"}), ["SRC-002"])
    expect("WGS84 out of range, lat/lon swapped", mutated(**{"source.input_wkid": 4326, "source.x": 32.0, "source.y": 120.0, "crs.wkid": None}), ["SRC-003", "SRC-004"])
    expect("height missing", mutated(**{"source.height_m": None}), ["SRC-014"])
    expect("negative height", mutated(**{"source.height_m": -1}), ["SRC-015"])
    expect("height 150 m", mutated(**{"source.height_m": 150}), ["SRC-016"])
    expect("height 0", mutated(**{"source.height_m": 0}), ["SRC-017"])
    # spectrum
    expect("empty spectrum", mutated(**{"source.spectrum.lw": [None] * 8}), ["SPC-001"])
    expect("one band missing", mutated(**{"source.spectrum.lw": [90, None, 90, 90, 90, 90, 90, 90]}), ["SPC-002"])
    expect("non-numeric band", mutated(**{"source.spectrum.lw": [90, "x", 90, 90, 90, 90, 90, 90]}), ["SPC-003"])
    expect("negative Lw", mutated(**{"source.spectrum.lw": [-5, 90, 90, 90, 90, 90, 90, 90]}), ["SPC-004"])
    expect("Lw 200", mutated(**{"source.spectrum.lw": [200, 90, 90, 90, 90, 90, 90, 90]}), ["SPC-005"])
    expect("all zeros", mutated(**{"source.spectrum.lw": [0.0] * 8}), ["SPC-006"])
    expect("flat spectrum", mutated(**{"source.spectrum.lw": [95.0] * 8}), ["SPC-007"])
    # directivity
    expect("omni note", base_scenario(), ["DIR-001"])
    expect("directional without Dc", mutated(**{"source.directivity.mode": "directional"}), ["DIR-002", "DIR-004"])
    expect("Dc 25 dB", mutated(**{"source.directivity.mode": "directional", "source.directivity.dc": [25] + [0] * 7}), ["DIR-003"])
    expect("heading not a number", mutated(**{"source.directivity.heading_deg": "x"}), ["DIR-005"])
    expect("heading 400", mutated(**{"source.directivity.heading_deg": 400}), ["DIR-006"])
    expect("angular table not supported", mutated(**{"source.directivity.angular_table": [[0, 1]]}), ["DIR-007"])
    # terrain
    expect("no DTM", base_scenario(), ["DTM-001"])
    expect("terrain screening off", mutated(**{"terrain.dtm": {"path": "x.tif"}, "terrain.screening": False}), ["DTM-016"])
    expect("DTM that does not exist (deep)", mutated(**{"terrain.dtm": {"path": os.path.join(outdir, "no.tif")}}), ["DTM-002"], deep=True)
    # area
    expect("no area", mutated(**{"area.mode": None}), ["ARA-001"])
    expect("polygon without rings", mutated(**{"area.mode": "polygon", "area.rings": []}), ["ARA-002"])
    expect("polygon with 2 points", mutated(**{"area.mode": "polygon", "area.rings": [[(0, 0), (1, 1)]]}), ["ARA-003"])
    expect("bow-tie polygon", mutated(**{"area.mode": "polygon", "area.rings": [[(0, 0), (2, 2), (2, 0), (0, 2)]]}), ["ARA-004"])
    expect("zero-area polygon", mutated(**{"area.mode": "polygon", "area.rings": [[(0, 0), (1, 1), (2, 2)]]}), ["ARA-005"])
    expect("radius 0", mutated(**{"area.mode": "radius", "area.radius_m": 0}), ["ARA-008"])
    expect("radius follows the source (note)", mutated(**{"area.mode": "radius", "area.radius_m": 200}), ["ARA-014"])
    expect("degenerate extent", mutated(**{"area.extent": [0, 0, 0, 10]}), ["ARA-011"])
    expect("cell size missing", mutated(**{"area.cell": {"mode": "custom", "size_m": None}}), ["ARA-016"])
    expect("match DTM without a DTM", mutated(**{"area.cell": {"mode": "match_dtm", "size_m": None}}), ["ARA-017"])
    expect("receiver height 0", mutated(**{"area.receiver_height_m": 0}), ["ARA-022"])
    expect("receiver height 80", mutated(**{"area.receiver_height_m": 80}), ["ARA-023"])
    expect("too many cells", mutated(**{"area.extent": [X0, Y0, X0 + 100000, Y0 + 100000], "area.cell": {"mode": "custom", "size_m": 10}}), ["ARA-019"])
    expect("coarse grid", mutated(**{"area.cell": {"mode": "custom", "size_m": 40}}), ["ARA-018"])
    expect("source outside the receiver area is allowed (note)", base_scenario(), ["ARA-013"], absent=["ARA-008"])
    # structures
    sc = base_scenario(); sc["structures"] = [building(name="A", sid="a"), building(name="A", sid="b")]
    expect("duplicate names", sc, ["STR-001"])
    sc = base_scenario(); sc["structures"] = [building(name="", sid="a")]
    expect("empty name", sc, ["STR-002"])
    sc = base_scenario(); sc["structures"] = [{"id": "a", "type": "tree", "name": "T"}]
    expect("unknown type", sc, ["STR-003"])
    sc = base_scenario(); sc["structures"] = [building(visible=False)]
    expect("hidden but included is stated", sc, ["STR-004"])
    sc = base_scenario(); sc["structures"] = [building(include=False)]
    expect("shown but excluded is stated", sc, ["STR-005"])
    sc = base_scenario(); sc["structures"] = [{"id": "a", "type": "building", "name": "B", "height_m": 5, "footprint": None}]
    expect("building without footprint", sc, ["BLD-001"])
    sc = base_scenario(); sc["structures"] = [building(ring=[(0, 0), (1, 1)])]
    expect("building with two vertices", sc, ["BLD-002"])
    sc = base_scenario(); sc["structures"] = [building(ring=[(0, 0), (2, 2), (2, 0), (0, 2)])]
    expect("building bow-tie", sc, ["BLD-003"])
    sc = base_scenario(); sc["structures"] = [building(h=None)]
    expect("building height missing", sc, ["BLD-004"])
    sc = base_scenario(); sc["structures"] = [building(h=-2)]
    expect("building height negative", sc, ["BLD-005"])
    sc = base_scenario(); sc["structures"] = [building(h=500)]
    expect("building height 500 m", sc, ["BLD-006"])
    sc = base_scenario(); sc["structures"] = [building(ring=[(X0 - 5, Y0 - 5), (X0 + 5, Y0 - 5), (X0 + 5, Y0 + 5), (X0 - 5, Y0 + 5)])]
    expect("source inside a building", sc, ["BLD-012"])
    sc = base_scenario(); sc["structures"] = [barrier(path=[(X0 + 20, Y0)])]
    expect("barrier with one vertex", sc, ["BAR-002"])
    sc = base_scenario(); b = barrier(); b["path"] = []; sc["structures"] = [b]
    expect("barrier without path", sc, ["BAR-001"])
    sc = base_scenario(); b = barrier(); b["vertical"]["mode"] = "x"; sc["structures"] = [b]
    expect("barrier unknown vertical definition", sc, ["BAR-007"])
    sc = base_scenario(); sc["structures"] = [barrier(h=None)]
    expect("barrier height missing", sc, ["BAR-004"])
    sc = base_scenario(); sc["structures"] = [barrier(h=-1)]
    expect("barrier height negative", sc, ["BAR-005"])
    sc = base_scenario(); sc["structures"] = [barrier(h=30)]
    expect("barrier height 30 m", sc, ["BAR-006"])
    sc = base_scenario(); sc["structures"] = [barrier(path=[(X0 - 20, Y0), (X0 + 20, Y0)])]
    expect("barrier through the source", sc, ["BAR-015"])
    sc = base_scenario(); sc["structures"] = [barrier(path=[(X0 + 20, Y0 - 30), (X0 + 20, Y0), (X0 + 40, Y0 + 30)])]
    expect("barrier with several segments", sc, ["BAR-017"])
    sc = base_scenario(); sc["structures"] = [barrier(path=[(X0 + 20, Y0), (X0 + 21, Y0)])]
    expect("very short barrier", sc, ["BAR-018"])
    sc = base_scenario(); b = barrier(); b["gap_m"] = -1; sc["structures"] = [b]
    expect("barrier negative gap", sc, ["BAR-026"])
    sc = base_scenario(); sc["structures"] = [barrier(transmission={"enabled": True, "material": None})]
    expect("transmission without material", sc, ["BAR-022"])
    sc = base_scenario(); sc["structures"] = [barrier(transmission={"enabled": True, "material": MASS_LAW(5.0)})]
    expect("barrier lighter than 10 kg/m2", sc, ["BAR-023", "BAR-025"])
    sc = base_scenario(); sc["structures"] = [barrier()]
    expect("diffraction-only is stated", sc, ["BAR-019", "BAR-024"])
    sc = base_scenario(); b = barrier(); b["placement"] = {"mode": "straight", "start": [X0 + 20, Y0 - 50], "length_m": None, "azimuth_deg": 0}; sc["structures"] = [b]
    expect("straight barrier missing length", sc, ["BAR-011"])
    sc = base_scenario(); b = barrier(); b["placement"] = {"mode": "straight", "start": [X0 + 20, Y0 - 50], "length_m": 100, "azimuth_deg": "n"}; sc["structures"] = [b]
    expect("straight barrier azimuth not a number", sc, ["BAR-012"])
    sc = base_scenario(); b = barrier(); b["placement"] = {"mode": "straight", "start": [X0 + 20, Y0 - 50], "length_m": 100, "azimuth_deg": 0}; sc["structures"] = [b]
    expect("straight barrier placement reports its end point", sc, ["BAR-013"])
    # enclosures
    sc = base_scenario(); sc["structures"] = [enclosure()]
    expect("enclosure ok: stated once, floor is ground, TL/alpha note", sc, ["ENC-023", "ENC-030", "ENC-035"],
           absent=["ENC-004", "ENC-009", "ENC-010"])
    sc = base_scenario(); e = enclosure(); e["source_link"] = None; sc["structures"] = [e]
    expect("enclosure not linked", sc, ["ENC-001"])
    sc = base_scenario(); e = enclosure(); e["mode"] = "polygon"; sc["structures"] = [e]
    expect("polygon enclosure without footprint", sc, ["ENC-002"])
    sc = base_scenario(); e = enclosure(); e["rect"]["length_m"] = None; sc["structures"] = [e]
    expect("enclosure without length", sc, ["ENC-003"])
    sc = base_scenario(); e = enclosure(); e["rect"]["offset"] = [20.0, 0.0]; sc["structures"] = [e]
    expect("source outside the enclosure", sc, ["ENC-004"])
    sc = base_scenario(); e = enclosure(h=0.5); sc["structures"] = [e]
    expect("source above the roof", sc, ["ENC-005"])
    sc = base_scenario(); e = enclosure(); e["faces"] = {"mode": "per_face", "all": None, "faces": {"Wall N": MASS_LAW(25)}}; sc["structures"] = [e]
    expect("per-face materials missing -> walls and roof", sc, ["ENC-007", "ENC-008"])
    sc = base_scenario(); e = enclosure(material=MANUF([10, None] + [20] * 6, [0.3] * 8)); sc["structures"] = [e]
    expect("TL missing in a band", sc, ["ENC-009"])
    sc = base_scenario(); e = enclosure(material=MANUF([20] * 8, [0.3, None] + [0.3] * 6)); sc["structures"] = [e]
    expect("alpha missing in a band", sc, ["ENC-010"])
    sc = base_scenario(); e = enclosure(material=MANUF([20] * 8, [2.0] + [0.3] * 7)); sc["structures"] = [e]
    expect("alpha 2.0 (not a coefficient)", sc, ["ENC-011"])
    sc = base_scenario(); e = enclosure(material=MANUF([-3] + [20] * 7, [0.3] * 8)); sc["structures"] = [e]
    expect("negative TL", sc, ["ENC-012"])
    sc = base_scenario(); e = enclosure(material=MANUF([120] + [20] * 7, [0.3] * 8)); sc["structures"] = [e]
    expect("TL 120 dB", sc, ["ENC-013"])
    sc = base_scenario(); m = MASS_LAW(None); e = enclosure(material=m); sc["structures"] = [e]
    expect("mass law without data", sc, ["ENC-014"])
    sc = base_scenario(); e = enclosure(material=MASS_LAW(-5)); sc["structures"] = [e]
    expect("negative surface mass", sc, ["ENC-015"])
    sc = base_scenario(); m = MASS_LAW(None); m.update({"thickness_m": 0.0, "volume_density_kg_m3": 2400}); sc["structures"] = [enclosure(material=m)]
    expect("zero thickness", sc, ["ENC-016"])
    sc = base_scenario(); m = MASS_LAW(None); m.update({"thickness_m": 0.1, "volume_density_kg_m3": 2400, "solid": False}); sc["structures"] = [enclosure(material=m)]
    expect("thickness x density for a non-solid layer", sc, ["ENC-017"])
    sc = base_scenario(); e = enclosure(); e["open_area_m2"] = 999.0; sc["structures"] = [e]
    expect("opening larger than the enclosure", sc, ["ENC-020"])
    sc = base_scenario(); e = enclosure(); e["open_area_m2"] = 1.0; sc["structures"] = [e]
    expect("small opening limits the reduction", sc, ["ENC-021"])
    sc = base_scenario(); sc["structures"] = [enclosure(sid="e1", name="E1"), enclosure(sid="e2", name="E2")]
    expect("two enclosures for one source", sc, ["ENC-027"])
    sc = base_scenario(); e = enclosure(include=False); sc["structures"] = [e]
    expect("excluded enclosure is stated", sc, ["ENC-024"])
    sc = base_scenario(); e = enclosure(h=None); sc["structures"] = [e]
    expect("enclosure height missing", sc, ["ENC-034"])
    sc = base_scenario(); e = enclosure(); e["faces"] = {"mode": "per_face", "all": None, "faces": {
        "Wall N": MASS_LAW(25), "Wall E": MANUF([20] * 8, [0.3] * 8), "Wall S": MASS_LAW(25), "Wall W": MASS_LAW(25), "Roof": MASS_LAW(25)}}; sc["structures"] = [e]
    expect("mixed measured and estimated faces", sc, ["ENC-028"])
    # propagation
    expect("G = 2", mutated(**{"propagation.ground.G": 2}), ["PRP-001"])
    expect("separate G missing", mutated(**{"propagation.ground.separate": True}), ["PRP-002"])
    expect("temperature 99", mutated(**{"propagation.atmosphere.T_C": 99}), ["PRP-005"])
    expect("humidity 0", mutated(**{"propagation.atmosphere.RH": 0}), ["PRP-006"])
    expect("pressure negative", mutated(**{"propagation.atmosphere.p_kPa": -1}), ["PRP-007"])
    expect("pressure in hPa", mutated(**{"propagation.atmosphere.p_kPa": 1013}), ["PRP-008"])
    expect("dry air", mutated(**{"propagation.atmosphere.RH": 5}), ["PRP-009"])
    expect("unknown mode", mutated(**{"propagation.mode": "x"}), ["PRP-010"])
    expect("draft mode", mutated(**{"propagation.mode": "draft2026"}), ["PRP-012"])
    expect("1996 mode", mutated(**{"propagation.mode": "iso1996"}), ["PRP-013"])
    expect("long-term without C0", mutated(**{"propagation.meteorology.method": "long_term"}), ["PRP-015"])
    expect("negative C0", mutated(**{"propagation.meteorology.method": "long_term", "propagation.meteorology.C0": -1}), ["PRP-016"])
    expect("C0 = 9", mutated(**{"propagation.meteorology.method": "long_term", "propagation.meteorology.C0": 9}), ["PRP-017", "PRP-018"])
    expect("C0 with favourable ignored", mutated(**{"propagation.meteorology.C0": 3}), ["PRP-019"])
    expect("active effects listed", base_scenario(), ["PRP-020", "PRP-021"])
    # outputs
    expect("no gdb", mutated(**{"outputs.gdb": None}), ["OUT-001"])
    expect("gdb is a folder", mutated(**{"outputs.gdb": "C:\\temp\\folder"}), ["OUT-003"])
    expect("gdb missing (deep)", mutated(**{"outputs.gdb": os.path.join(outdir, "none.gdb")}), ["OUT-002"], deep=True)
    expect("empty run name", mutated(**{"outputs.run_name": ""}), ["OUT-005"])
    expect("run name with a space", mutated(**{"outputs.run_name": "my run"}), ["OUT-006"])
    expect("no output chosen", mutated(**{"outputs.overall_a": False}), ["OUT-008"])
    expect("bad band", mutated(**{"outputs.bands": [3]}), ["OUT-009", "OUT-010"])
    expect("bad colour scale", mutated(**{"outputs.shared_scale": {"min": 60, "max": 40}}), ["OUT-012"])
    expect("limit not a number", mutated(**{"outputs.limit_dba": "x"}), ["OUT-014"])
    expect("dataset names are listed", base_scenario(), ["OUT-011"])

    print("\n=== 6. Participation vs visibility ===")
    from noisebox import scenario_run as R
    s1 = base_scenario(gdb); s1["structures"] = [barrier(visible=True)]
    s2 = base_scenario(gdb); s2["structures"] = [barrier(visible=False)]
    s3 = base_scenario(gdb); s3["structures"] = [barrier(include=False, visible=True)]
    o1, _ = R.obstacles_job(s1, R.resolve_scene(s1))
    o2, _ = R.obstacles_job(s2, R.resolve_scene(s2))
    o3, _ = R.obstacles_job(s3, R.resolve_scene(s3))
    report("hiding the drawing leaves the engine obstacles unchanged", o1 == o2 and len(o1) == 1)
    report("excluding it (even if drawn) removes them", o3 == [])
    p = R.preview(s2, deep=False)
    st = p["structures"][0]
    report("preview states participation and visibility separately",
           "in the run" in st["state"] and "hidden" in st["state"], st["state"])
    sm = SC.section_summaries(s1)
    report("collapsed-section summaries", sm["source"] == "Source 1, 1 m above ground"
           and "1 active barrier" in sm["structures"], str(sm))

    print("\n=== 7. Save / load / duplicate ===")
    path = SC.save(s1, os.path.join(outdir, "s1.json"))
    back, iss = SC.load(path)
    report("save and reload gives the same scenario", back["structures"] == s1["structures"] and back["source"] == s1["source"])
    d = SC.duplicate(s1, "copy")
    report("duplicate has a new id and name", d["id"] != s1["id"] and d["name"] == "copy" and d["structures"] == s1["structures"])
    with open(os.path.join(outdir, "bad.json"), "w", encoding="utf-8") as f:
        f.write("{not json")
    report("invalid file -> SCN-002", SC.load(os.path.join(outdir, "bad.json"))[1][0].code == "SCN-002")
    report("missing file -> SCN-001", SC.load(os.path.join(outdir, "gone.json"))[1][0].code == "SCN-001")
    old = dict(s1); old["schema"] = "noisebox.scenario/99"
    SC.save(old, os.path.join(outdir, "old.json"))
    # save() keeps the given schema; load must reject it
    report("other schema version -> SCN-003", SC.load(os.path.join(outdir, "old.json"))[1][0].code == "SCN-003")

    allcodes = set(I.CATALOGUE)
    print("\nCatalogue coverage by these tests: %d of %d codes were triggered (the rest need a DTM, an engine run or "
          "special GIS data; see test_scenario_engine.py)" % (len(SEEN & allcodes), len(allcodes)))
    print("\nALL PASS" if all(RESULTS) else "\nSOME FAILED (%d of %d)" % (RESULTS.count(False), len(RESULTS)))
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
