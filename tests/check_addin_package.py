"""Static checks of the built add-in (no ArcGIS Pro needed):
  1. Config.daml is well-formed and validates against Esri's schema (ArcGIS.Desktop.Framework.xsd in the Pro install);
  2. every className in the DAML names a class that exists in the compiled assembly (read with System.Reflection.Metadata
     through a tiny PowerShell helper) -- here approximated by scanning the compiled DLL's metadata strings;
  3. the .esriAddinX is a zip with Config.daml at the root and the assembly under Install/.
Usage: python tests\\check_addin_package.py
"""
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAML = os.path.join(ROOT, "addin", "NoiseBoxAddin", "Config.daml")
DLL = os.path.join(ROOT, "addin", "NoiseBoxAddin", "bin", "Release", "net8.0-windows", "NoiseBoxAddin.dll")
PKG = os.path.join(ROOT, "dist", "NoiseBox.esriAddinX")
XSD = r"C:\Program Files\ArcGIS\Pro\bin\ArcGIS.Desktop.Framework.xsd"
RES = []


def report(name, ok, detail=""):
    RES.append(bool(ok))
    print("RESULT %-64s %s %s" % (name, "PASS" if ok else "FAIL", detail))


def main():
    tree = ET.parse(DAML)
    ns = {"d": "http://schemas.esri.com/DADF/Registry"}
    report("Config.daml is well-formed XML", True)

    # 1. schema validation through .NET (PowerShell), the same schema Pro uses
    ps = ("$ErrorActionPreference = 'Stop'; "
          "$s = New-Object System.Xml.Schema.XmlSchemaSet; $s.Add('http://schemas.esri.com/DADF/Registry', '%s') | Out-Null; "
          "$settings = New-Object System.Xml.XmlReaderSettings; $settings.Schemas = $s; $settings.ValidationType = 'Schema'; "
          "$script:errs = @(); $settings.add_ValidationEventHandler({ param($sender,$e) $script:errs += $e.Message }); "
          "$r = [System.Xml.XmlReader]::Create('%s', $settings); while ($r.Read()) {}; $r.Close(); "
          "if ($script:errs.Count -eq 0) { 'XSD-OK' } else { $script:errs | Select-Object -First 8 }" % (XSD, DAML))
    p = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    out = (p.stdout + p.stderr).strip()
    report("Config.daml validates against Esri's ArcGIS.Desktop.Framework.xsd", "XSD-OK" in out, out[:600] if "XSD-OK" not in out else "")
    # the same check must FAIL on a corrupted copy, otherwise it proves nothing
    bad = os.path.join(os.environ.get("TEMP", "."), "nb_bad.daml")
    txt = open(DAML, encoding="utf-8").read().replace("<tabs>", "<tabz>").replace("</tabs>", "</tabz>").replace('caption="Set Location"', 'captionX="Set Location"')
    open(bad, "w", encoding="utf-8").write(txt)
    p2 = subprocess.run(["powershell", "-NoProfile", "-Command", ps.replace(DAML, bad)], capture_output=True, text=True)
    report("the schema check rejects a corrupted copy (so the pass above is real)", "XSD-OK" not in (p2.stdout + p2.stderr), (p2.stdout + p2.stderr).strip()[:160])

    # 2. classNames exist in the assembly
    names = set()
    for el in tree.iter():
        cn = el.attrib.get("className")
        if cn:
            names.add(cn)
    data = open(DLL, "rb").read()
    missing = []
    for cn in sorted(names):
        short = cn.split(".")[-1]
        if short.encode("utf-8") not in data:
            missing.append(cn)
    report("all %d classNames in the DAML exist in the compiled assembly" % len(names), not missing, str(missing))

    # ids referenced by refID exist
    ids = {el.attrib["id"] for el in tree.iter() if "id" in el.attrib}
    refs = {el.attrib["refID"] for el in tree.iter() if "refID" in el.attrib}
    unknown = sorted(r for r in refs if r not in ids and not r.startswith("esri_"))
    report("every refID in the DAML points at a defined control", not unknown, str(unknown))
    groups = [g.attrib["id"] for g in tree.iter("{%s}group" % ns["d"]) if "caption" in g.attrib]
    report("the tab has the six groups", len(groups) == 6, ", ".join(g.replace("NoiseBox_Group_", "") for g in groups))

    # 3. package
    if os.path.isfile(PKG):
        z = zipfile.ZipFile(PKG)
        n = z.namelist()
        report("package: Config.daml at the root, assembly under Install/", "Config.daml" in n and "Install/NoiseBoxAddin.dll" in n, str(n[:4]))
        refs = set(re.findall(r'(?:smallImage|largeImage|image)="([^"]+)"', open(DAML, encoding="utf-8").read()))
        miss_src = [r for r in refs if not os.path.exists(os.path.join(os.path.dirname(DAML), r))]
        miss_pkg = [r for r in refs if r not in n]
        report("icons: every image in Config.daml exists on disk (%d)" % len(refs), refs and not miss_src, str(miss_src[:5]))
        report("icons: every image in Config.daml is inside the package", refs and not miss_pkg, str(miss_pkg[:5]))
    else:
        report("package exists (run setup\\build_addin.ps1)", False)
    print("\nALL PASS" if all(RES) else "\nSOME FAILED")
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
