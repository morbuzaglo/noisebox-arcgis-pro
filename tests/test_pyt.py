"""Run the NoiseBox.pyt tools through ArcPy's geoprocessing framework (propy, outside the Pro GUI).
Checks the parameter layout (sections, defaults) and executes each tool.
Usage: propy tests\\test_pyt.py <outdir>
"""
import importlib.util
import os
import sys

from common import *  # noqa: F401,F403

PYT = os.path.join(ROOT, "NoiseBox.pyt")


def load_pyt():
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader("NoiseBoxPyt", PYT)
    spec = importlib.util.spec_from_loader("NoiseBoxPyt", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def main():
    outdir = sys.argv[1]
    gdb = fresh_gdb(outdir, "pyt")
    ok = True

    print("--- parameter layout (sections and defaults) ---")
    mod = load_pyt()
    for cls in (mod.CreateInputLayers, mod.NoiseMap, mod.NoiseAtReceivers, mod.CompareNoiseMaps, mod.CheckMatlabLink):
        t = cls()
        ps = t.getParameterInfo()
        cats = []
        for p in ps:
            if p.category and p.category not in cats:
                cats.append(p.category)
        print("%-34s [%s] %2d params; sections: %s" % (t.label, t.category, len(ps), cats))
    nm = {p.name: p for p in mod.NoiseMap().getParameterInfo()}
    defaults = {k: nm[k].value for k in ("G", "hr", "T", "RH", "mode", "overall", "iso_step", "detail", "add_map",
                                         "def_h", "def_lw", "run_name")}
    print("defaults:", defaults)
    ok &= nm["G"].value == 0.5 and nm["overall"].value == 55.0 and nm["sources_draw"].datatype == "Feature Set"
    drawn_ok = nm["sources_draw"].value is not None
    print("sketch template attached to 'draw sources' parameter:", drawn_ok)
    ok &= drawn_ok

    tb = arcpy.ImportToolbox(PYT, "noisebox")
    print("Tools in toolbox:", [t for t in dir(tb) if not t.startswith("_")])

    print("\n--- CheckMatlabLink ---")
    r = tb.CheckMatlabLink()
    print(r.getMessages().encode("ascii", "replace").decode()[-420:])

    print("\n--- CreateInputLayers ---")
    r = tb.CreateInputLayers(out_gdb=gdb, prefix="NB_", sr=SR, add_map=False)
    print(r.getMessages().encode("ascii", "replace").decode()[-300:])

    print("\n--- NoiseMap (picked layers, DEM, limits, bands, detail) ---")
    r = tb.NoiseMap(
        sources=os.path.join(GDB, "sources"), h_field="h_src", lw_prefix="Lw_",
        barriers=os.path.join(GDB, "barrier"), b_field="h_bar", dem=DEM_SAMPLE,
        G=0.5, hr=1.5, T=15, RH=70, mode="iso2024",
        extent="%f %f %f %f" % (X0 + 30, Y0 - 30, X0 + 130, Y0 + 30), cell=10,
        overall=45, lim500=40, out_gdb=gdb, run_name="pyt", iso_step=5, bands=True, detail="Full",
        copy_inputs=True, add_map=False)
    print(r.getMessages().encode("ascii", "replace").decode()[-900:])
    for nm_ in ("pyt_LAeq", "pyt_Margin", "pyt_PassFail", "pyt_Cells", "pyt_Bands", "pyt_Lp1000", "pyt_Summary"):
        e = arcpy.Exists(os.path.join(gdb, nm_))
        print("  exists %-14s %s" % (nm_, e))
        ok &= e

    print("\n--- NoiseAtReceivers ---")
    r = tb.NoiseAtReceivers(
        sources=os.path.join(GDB, "sources"), h_field="h_src", barriers=os.path.join(GDB, "barrier"), b_field="h_bar",
        G=0.5, hr=1.5, T=15, RH=70, mode="iso2024", receivers=os.path.join(GDB, "receivers"),
        overall=45, out_gdb=gdb, run_name="rcv", detail="Full", add_map=False)
    print(r.getMessages().encode("ascii", "replace").decode()[-500:])
    ok &= arcpy.Exists(os.path.join(gdb, "rcv_Receivers"))

    print("\n--- CompareNoiseMaps ---")
    r = tb.CompareNoiseMaps(baseline=os.path.join(gdb, "pyt_LAeq"), scenario=os.path.join(gdb, "pyt_LAeq"),
                            threshold=3, out_gdb=gdb, run_name="cmp", add_map=False)
    print(r.getMessages().encode("ascii", "replace").decode()[-300:])

    print("\n--- Error path: bad Lw prefix ---")
    try:
        tb.NoiseMap(sources=os.path.join(GDB, "sources"), h_field="h_src", lw_prefix="Nope_", G=0.5, hr=1.5, T=15,
                    RH=70, mode="iso2024", cell=10, out_gdb=gdb, run_name="bad", add_map=False)
        ok = False
    except arcpy.ExecuteError:
        print(arcpy.GetMessages(2).encode("ascii", "replace").decode()[:300])
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
