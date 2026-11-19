"""Static audit of the pane: every {Binding Path} in NoiseBoxPaneView.xaml must name a public member of the view model
(or of the item types used in templates), every event handler must exist in the code-behind, every x:Static converter must
exist, and every Fields[...] / SF[...] / MF[...] key must be registered. WPF bindings fail silently at run time, so this
catches typos that the compiler cannot. Usage: python tests\\check_xaml_bindings.py"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "addin", "NoiseBoxAddin", "UI")
xaml = open(os.path.join(UI, "NoiseBoxPaneView.xaml"), encoding="utf-8").read()
vm_src = "".join(open(f, encoding="utf-8").read() for f in glob.glob(os.path.join(UI, "NoiseBoxPaneViewModel*.cs")))
code_behind = open(os.path.join(UI, "NoiseBoxPaneView.xaml.cs"), encoding="utf-8").read()
all_ui = vm_src + code_behind
RES = []


def report(name, ok, detail=""):
    RES.append(bool(ok))
    print("RESULT %-66s %s %s" % (name, "PASS" if ok else "FAIL", detail))


members = set(re.findall(r"public\s+(?:static\s+)?(?:readonly\s+)?[\w<>\[\],\.\? ]+?\s+(\w+)\s*(?:\{|=>|=|;)", vm_src))
members |= set(re.findall(r"public\s+[\w<>\[\],\.\? ]+?\s+(\w+)\s*\(", vm_src))
# item types used inside templates
item_members = set()
for cls in ("StructureItem", "BandRow", "BandChoice", "ProfilePoint", "Issue", "PointCandidate", "LayerItem"):
    for f in glob.glob(os.path.join(ROOT, "addin", "NoiseBoxAddin", "**", "*.cs"), recursive=True):
        s = open(f, encoding="utf-8").read()
        m = re.search(r"class\s+%s\b.*?(?=\n    (?:internal|public)\s+(?:sealed\s+|partial\s+)?class|\Z)" % cls, s, flags=re.S)
        if m:
            item_members |= set(re.findall(r"public\s+[\w<>\[\],\.\? ]+?\s+(\w+)\s*(?:\{|=>)", m.group(0)))
templated = {"Hz", "Text", "Name", "Type", "Include", "Visible", "State", "Icon", "Save", "Label", "Count", "IsChecked", "Content"}

paths = re.findall(r"\{Binding\s+([^,}\s]+)", xaml)
bad = []
for p in paths:
    if p.startswith(("RelativeSource", "ElementName", "Path=")):
        continue
    first = re.split(r"[.\[]", p)[0]
    if first in members or first in item_members or first in templated:
        continue
    bad.append(p)
report("all %d binding paths resolve to a public member" % len(paths), not bad, str(sorted(set(bad))))

keys_used = {"Fields": set(re.findall(r"Fields\[(\w+)\]", xaml)), "SF": set(re.findall(r"SF\[(\w+)\]", xaml)), "MF": set(re.findall(r"MF\[(\w+)\]", xaml))}
reg = {"Fields": set(re.findall(r'Fields\.(?:Num|Str)\("(\w+)"', vm_src)), "SF": set(re.findall(r'SF\.(?:NumDyn|StrDyn)\("(\w+)"', vm_src)),
       "MF": set(re.findall(r'MF\.(?:NumDyn|StrDyn)\("(\w+)"', vm_src))}
miss = {k: sorted(keys_used[k] - reg[k]) for k in keys_used if keys_used[k] - reg[k]}
report("every Fields[...] / SF[...] / MF[...] key is registered in the view model", not miss, str(miss))

handlers = set(re.findall(r'(?:Click|PreviewKeyDown|MouseDoubleClick|SelectionChanged)="(\w+)"', xaml))
nohandler = sorted(h for h in handlers if not re.search(r"void\s+%s\s*\(" % h, code_behind))
report("every event handler in the XAML exists in the code-behind", not nohandler, str(nohandler))

conv = set(re.findall(r"ui:Inverse\.(\w+)", xaml))
noconv = sorted(c for c in conv if not re.search(r"static readonly IValueConverter %s\b" % c, code_behind))
report("every converter used in the XAML is defined", not noconv, str(noconv))

focus = set(re.findall(r'x:Name="f_(\w+)"', xaml))
keys = set(re.findall(r'return "(\w+)";', vm_src)) | set(re.findall(r'Open\("\w+", "(\w+)"\)', open(os.path.join(ROOT, "addin", "NoiseBoxAddin", "Buttons.cs"), encoding="utf-8").read())) \
    | set(re.findall(r'Show\("\w+", "(\w+)"\)', open(os.path.join(ROOT, "addin", "NoiseBoxAddin", "Buttons.cs"), encoding="utf-8").read()))
keys |= {"sname", "heading"}
nofocus = sorted(k for k in keys if k not in focus and k not in ("lw",))
report("every field the issue list can focus has a matching x:Name", not nofocus, str(nofocus))
print("\nALL PASS" if all(RES) else "\nSOME FAILED")
sys.exit(0 if all(RES) else 1)
