"""Builds docs/NoiseBox_Manual.html and the PDF (Edge headless print). Run with propy:   propy docs\\build_manual.py
All pictures of the software are REAL screenshots taken from ArcGIS Pro 3.5.3 while the worked example was run by the
automated test (docs/figures/ui). The result maps and numbers come from the geodatabase of those runs."""
import html
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from noisebox import issues as I  # noqa: E402

UI = os.path.join(HERE, "figures", "ui")
NUM = json.load(open(os.path.join(UI, "example_numbers.json"), encoding="utf-8")) if os.path.isfile(os.path.join(UI, "example_numbers.json")) else {}
TS = json.load(open(os.path.join(HERE, "test_summary.json"), encoding="utf-8")) if os.path.isfile(os.path.join(HERE, "test_summary.json")) else {}
VERSION = "1.20"
SECTION_NAMES = {"SCN": "Scenario file and coordinate system", "SRC": "Source location and height", "SPC": "Source spectrum",
                 "DIR": "Directivity", "DTM": "Terrain (DTM)", "ARA": "Receiver area and grid", "STR": "Structures (general)",
                 "BLD": "Buildings", "BAR": "Noise barriers", "ENC": "Enclosures", "PRP": "Propagation settings",
                 "OUT": "Outputs and allowed levels", "ENG": "Engine and run"}


def esc(s):
    return html.escape(str(s))


_FIGN = [0]


def fig(name, cap, width="100%", small=False):
    _FIGN[0] += 1
    cap = "Figure %d. %s" % (_FIGN[0], cap)
    path = os.path.join(UI, name)
    if not os.path.isfile(path):
        return "<div class='box bad'>missing figure %s</div>" % esc(name)
    return "<div class='fig'><img src='figures/ui/%s' style='max-width:%s'><div class='cap'>%s</div></div>" % (name, width, esc(cap))


def fnum(x, d=1):
    return "?" if x is None else ("%.*f" % (d, x))


def catalogue_html():
    out = []
    groups = {}
    for code, (sev, sec, msg, fix) in I.CATALOGUE.items():
        groups.setdefault(code[:3], []).append((code, sev, msg, fix))
    for pre, rows in groups.items():
        out.append("<h3>%s (%s-xxx, %d entries)</h3><table class='cat'><tr><th>Code</th><th>Type</th><th>Message</th><th>What to do</th></tr>" % (SECTION_NAMES[pre], pre, len(rows)))
        for code, sev, msg, fix in rows:
            out.append("<tr class='%s'><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (sev, code, sev, esc(msg), esc(fix)))
        out.append("</table>")
    return "\n".join(out)


def step(n, title, text):
    return "<div class='step'><div class='num'>%s</div><div class='body'><b>%s</b><br>%s</div></div>" % (n, title, text)


css = """
@page { size: A4; margin: 17mm 15mm 17mm 15mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', Arial, sans-serif; color: #1c2430; font-size: 10pt; line-height: 1.45; }
h1 { font-size: 27pt; color: #1f3b5c; margin: 0 0 4pt 0; }
h2 { font-size: 15.5pt; color: #1f3b5c; border-bottom: 2px solid #2f6fa8; padding-bottom: 3pt; margin-top: 20pt; page-break-after: avoid; }
h3 { font-size: 11.8pt; color: #2f6fa8; margin: 13pt 0 4pt; page-break-after: avoid; }
.cover { height: 250mm; display: flex; flex-direction: column; justify-content: center; page-break-after: always; }
.cover .sub { font-size: 14pt; color: #4b5563; margin-bottom: 26pt; }
.cover .meta { color: #6b7280; font-size: 10pt; border-top: 1px solid #d1d5db; padding-top: 8pt; margin-top: 26pt; }
.pb { page-break-before: always; }
.box { border-left: 4px solid #2f6fa8; background: #eef4fb; padding: 6pt 10pt; margin: 8pt 0; page-break-inside: avoid; }
.warn { border-left-color: #d9822b; background: #fff6ea; } .bad { border-left-color: #b42318; background: #fdecea; } .ok { border-left-color: #2e7d32; background: #edf7ee; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0; font-size: 9.2pt; }
th { background: #1f3b5c; color: white; text-align: left; padding: 4pt 6pt; }
td { border-bottom: 1px solid #e5e7eb; padding: 3.3pt 6pt; vertical-align: top; } tr { page-break-inside: avoid; }
table.cat { font-size: 7.5pt; } table.cat td { padding: 2pt 4pt; }
table.cat tr.error td:nth-child(2) { color: #b42318; font-weight: 600; } table.cat tr.warning td:nth-child(2) { color: #b26200; font-weight: 600; } table.cat tr.info td:nth-child(2) { color: #6b7280; }
.step { display: flex; gap: 9pt; margin: 8pt 0; page-break-inside: avoid; }
.num { flex: 0 0 22pt; height: 22pt; border-radius: 50%; background: #2f6fa8; color: white; text-align: center; line-height: 22pt; font-weight: 700; }
.step .body { flex: 1; }
.fig { text-align: center; margin: 7pt 0; page-break-inside: avoid; } .fig img { border: 1px solid #d1d5db; }
.cap { font-size: 8.5pt; color: #6b7280; margin-top: 2pt; }
.two3 { display: flex; gap: 8pt; } .two3 .fig { flex: 1; margin: 4pt 0; }
.two { display: flex; gap: 12pt; align-items: flex-start; } .two > div { flex: 1; }
.pane { display: flex; gap: 12pt; align-items: flex-start; } .pane .fig { flex: 0 0 41%; margin: 0; } .pane .txt { flex: 1; }
code, .k { font-family: Consolas, monospace; background: #f1f3f5; padding: 0 3pt; border-radius: 2pt; font-size: 9pt; }
pre { background: #f1f3f5; padding: 7pt 9pt; border-radius: 4pt; font-size: 8.6pt; white-space: pre-wrap; }
.toc li { margin: 2pt 0; } .yes { color: #2e7d32; font-weight: 600; } .no { color: #b42318; font-weight: 600; } .part { color: #b26200; font-weight: 600; }
ul, ol { margin: 4pt 0 4pt 18pt; padding: 0; }
"""

tests_html = "".join("<tr><td>%s</td><td>%s</td></tr>" % (esc(a), esc(b)) for a, b in TS.get("lines", []))
A, B = NUM.get("A", {}), NUM.get("B", {})
sA, sB = NUM.get("summary_A", {}), NUM.get("summary_B", {})

INSTALL = {
    1: step(1, "Copy the NoiseBox folder", "Copy the whole folder to the computer (a clone of the GitHub repository works too). Do not install into a protected folder."),
    2: step(2, "Run the setup once", "Open PowerShell in the folder and run <code>.\\setup\\setup_noisebox.ps1</code> (add <code>-MatlabRoot \"D:\\MATLAB\\R2023a\"</code> if MATLAB is not in <code>C:\\Program Files\\MATLAB</code>). It creates <code>%LOCALAPPDATA%\\NoiseBox\\venv310</code>, installs numpy and the MATLAB Engine into it, and tells the add-in where the folder is."),
    3: step(3, "Install the add-in", "Close ArcGIS Pro. Double-click <code>dist\\NoiseBox.esriAddinX</code> and choose <b>Install</b>. Without a dialog: <code>\"C:\\Program Files\\ArcGIS\\Pro\\bin\\RegisterAddIn.exe\" dist\\NoiseBox.esriAddinX /s</code>. Do not copy files into the add-in folders by hand: Pro keeps its own copy."),
    4: step(4, "Start ArcGIS Pro", "Open a project with a map or a scene. The <b>NoiseBox</b> tab appears next to Help (figure 1). If it does not: <i>Project &gt; Add-In Manager</i>."),
    5: step(5, "Check the MATLAB link", "In Catalog, add the toolbox <code>NoiseBox.pyt</code> and run <b>4. Utilities &gt; Check MATLAB Link</b>. It starts MATLAB once, runs a smoke case (expect 45.22 dB(A)) and shows that the <code>.m</code> files it ran are the ones in <code>matlab\\core</code>."),
}

body = f"""
<div class="cover">
  <h1>NoiseBox for ArcGIS Pro</h1>
  <div class="sub">User manual: installation, every setting, and a worked example with screenshots</div>
  <div class="box ok"><b>Status of this version ({VERSION}).</b> The ribbon add-in was installed in <b>ArcGIS Pro 3.5.3</b> and used
  on this computer: every screenshot in this manual is a real screenshot of the running software, and the worked example (section 8) was run from
  the pane, through MATLAB R2023a, to results in Contents. What was <i>not</i> tested is listed in section 13.</div>
  <div class="meta">ArcGIS Pro 3.5 or later &nbsp;|&nbsp; MATLAB R2022b to R2024b (tested: R2023a) &nbsp;|&nbsp; Python 3.10 for the MATLAB link<br>
  Prediction method: ISO 9613-2:2024 (default), the draft amendment and the 1996 edition selectable &nbsp;|&nbsp; No ISO certification or conformance is claimed.</div>
</div>

<h2 style="margin-top:0">Contents</h2>
<ol class="toc">
<li>What NoiseBox does</li><li>What you need</li><li>Installing on a computer</li><li>The workspace: ribbon, pane, Contents</li>
<li>Every setting, section by section</li><li>Allowed levels: overall and per octave band</li><li>Objects you create appear in Contents</li>
<li>Worked example: a drill rig behind a 4 m barrier, step by step</li><li>Reading the results</li><li>Speed: the MATLAB engine</li>
<li>Errors and warnings</li><li>What the engine calculates and what it does not</li><li>What was tested, and what was not</li><li>Troubleshooting</li>
<li>Appendix A: every error, warning and note &nbsp; B: scenario file, command line, configuration</li></ol>

<h2>1. What NoiseBox does</h2>
<p>NoiseBox predicts the sound level of a point source at every cell of a grid, the way ISO 9613-2 describes it, and puts the result on your map. You describe a
<b>scenario</b>: a source with its sound power spectrum, the terrain, a receiver area and, if you like, buildings, noise barriers and an enclosure around the source.
NoiseBox checks the scenario, calculates it in <b>your own validated MATLAB code</b> and adds a named group of rasters to <i>Contents</i>. Change one thing (a taller barrier) and run again to compare.</p>
<div class="two"><div><h3>Checked before anything runs</h3>
<p>Every input is checked. A problem is a numbered message that says what is wrong, why it matters and what to do; clicking it jumps to the input. There are {len(I.CATALOGUE)} such messages (Appendix A).</p></div>
<div><h3>How the pieces fit</h3>
<p>The ribbon and pane write a <b>scenario file</b>. Pro's Python reads it and sends the numeric job to a small worker in Python 3.10 that owns MATLAB. MATLAB runs the files in <code>matlab\\core</code>. No acoustics are calculated anywhere else, so editing a <code>.m</code> file changes the next run.</p></div></div>

<h2>2. What you need</h2>
<table><tr><th>Item</th><th>Version</th><th>Notes</th></tr>
<tr><td>ArcGIS Pro</td><td>3.5 or later</td><td>Tested with 3.5.3.</td></tr>
<tr><td>MATLAB</td><td>R2022b to R2024b</td><td>Licensed on that computer; no toolboxes are used. Tested with R2023a.</td></tr>
<tr><td>Python 3.10 (64-bit)</td><td>3.10.x</td><td>From python.org. Needed only because MATLAB's Python engine does not run in Pro's Python 3.11. Used in its own environment.</td></tr>
<tr><td>The NoiseBox folder</td><td>&nbsp;</td><td>Copy it anywhere (a folder that OneDrive or Dropbox syncs is best avoided).</td></tr>
<tr><td>A DTM raster (optional)</td><td>any single-band elevation raster</td><td>Or the ground surface of your map. Without a DTM the ground is flat at 0 m.</td></tr>
<tr><td><i>Only to rebuild the add-in:</i> .NET SDK</td><td>8 or newer</td><td>Not needed to use it.</td></tr></table>

<h2 class="pb">3. Installing on a computer</h2>
{INSTALL[1]}
{INSTALL[2]}
{INSTALL[3]}
{INSTALL[4]}
{INSTALL[5]}
<div class="box">The computer that <i>uses</i> the add-in needs no .NET SDK. To rebuild it after changing the C# code: <code>.\\setup\\build_addin.ps1</code>, then raise the <code>version</code> in <code>addin\\NoiseBoxAddin\\Config.daml</code> before installing: Pro keeps the old copy of an add-in whose version number did not change.</div>

<h2 class="pb">4. The workspace: ribbon, pane, Contents</h2>
{fig("01_ribbon.png", "The NoiseBox tab: six groups. Hover over any button in Pro for its tooltip; every button has a keytip (press Alt, then NB).")}
<table><tr><th>Group</th><th>Button</th><th>What it does</th></tr><tr><td>Scenario</td><td>New / Open / Save / Duplicate</td><td>A scenario is one <code>.nbscenario.json</code> file. Duplicate copies it to test a mitigation next to the baseline. The GIS data it refers to is never changed.</td></tr><tr><td>Source</td><td>Location (menu)</td><td>Three equivalent ways to set the source position: from a layer, enter coordinates, place on the map.</td></tr><tr><td>Source</td><td>Source Spectrum</td><td>Opens the pane at the Lw table: type, paste, import CSV, load a named profile.</td></tr><tr><td>Source</td><td>Directivity</td><td>Omnidirectional, or a constant correction Dc per band.</td></tr><tr><td>Terrain and Area</td><td>DTM (menu)</td><td>Project raster, <b>map ground surface</b>, browse for a file, show coverage, or flat ground.</td></tr><tr><td>Terrain and Area</td><td>Area (menu)</td><td>Existing polygons, draw a polygon or rectangle, radius around the source, capture the map extent.</td></tr><tr><td>Terrain and Area</td><td>Receiver Grid</td><td>Cell size (match the DTM or custom) and receiver height above local ground.</td></tr><tr><td>Structures</td><td>Building (menu)</td><td>From a polygon layer or draw a footprint.</td></tr><tr><td>Structures</td><td>Barrier (menu)</td><td>From a line layer, sketch on the map, or precise placement (start point, length, azimuth, height).</td></tr><tr><td>Structures</td><td>Enclosure (menu)</td><td>A quick rectangle around the source, or draw a footprint.</td></tr><tr><td>Propagation</td><td>Ground, Atmosphere, Terrain Screening, Meteorology</td><td>Open the pane at those settings (section 5.4).</td></tr><tr><td>Analysis</td><td>Preview</td><td>Fast check with no acoustic calculation: shows what the run will use and lists every issue.</td></tr><tr><td>Analysis</td><td>Run</td><td>Calculates with the MATLAB core and adds a named group to Contents.</td></tr><tr><td>Analysis</td><td>Results</td><td>Shows the datasets and run snapshots written so far.</td></tr></table>
<h3>The menus</h3>
<p>Buttons with a small arrow open a menu; the first item is also the button itself. Every item sets or adds something in the scenario and opens the pane at the right place.</p>
<div class="two3">{fig("m1_set_location_c.png", "Location menu.")}{fig("m2_select_dtm_c.png", "DTM menu with DTM from Map Ground.")}{fig("m3_set_area_c.png", "Area menu.")}</div>
<div class="two3">{fig("m4_building_c.png", "Building menu.")}{fig("m5_barrier_c.png", "Barrier menu.")}{fig("m6_enclosure_c.png", "Enclosure menu.")}</div>
<h3>The pane</h3>
<p>One dockable pane holds everything. Each section can be collapsed; a collapsed section shows a real summary of what is set in it. <b>Preview</b> and <b>Run</b> stay at the bottom with the number of errors and warnings and a status line.</p>
{fig("02_pane_new.png", "The whole window with a new scenario: ribbon, Contents (left), map, and the NoiseBox pane (right).", "92%")}

<h2 class="pb">5. Every setting, section by section</h2>
<h3>5.1 Source</h3>
<div class="pane">{fig("03_source.png", "Source section.")}<div class="txt">
<table><tr><th>Setting</th><th>Meaning</th></tr>
<tr><td>Source name</td><td>Label used in messages and in the <i>NoiseBox source</i> layer.</td></tr>
<tr><td>Location: from layer</td><td>The selected point of a point layer, or one found by name or ID (SRC-xxx messages explain a missing selection or several matches).</td></tr>
<tr><td>Location: coordinates</td><td>A coordinate pair in a system you choose (EPSG code). The labels say which order to type (Easting, Northing, or Latitude, Longitude). One conversion to the analysis system is done, once; all three location methods give the same point (tested to 2e-10 m).</td></tr>
<tr><td>Source height above ground (m)</td><td>The physical height of the source. It is <b>not</b> the ground elevation: the pane shows &ldquo;Ground 21.00 m + height 1.20 m = 22.20 m absolute&rdquo; once a DTM is chosen.</td></tr>
<tr><td>Spectrum Lw (dB re 1 pW)</td><td>Eight octave bands, 63 to 8000 Hz. <b>An empty cell is missing, not 0 dB</b>; a missing band stops the run and is named. Paste (8 numbers or frequency + level) from Excel or MATLAB, import a CSV, or load/save a named profile. The bar chart under the table shows the spectrum.</td></tr>
<tr><td>Directivity</td><td>Omnidirectional, or a constant correction Dc (dB, positive = louder) per band applied in all directions. A heading is stored; an angular table is not supported yet (a message says so).</td></tr></table></div></div>

<h3>5.2 Terrain and Area</h3>
<div class="pane">{fig("04_terrain.png", "Terrain and Area section, after choosing the map's ground surface.")}<div class="txt">
<table><tr><th>Setting</th><th>Meaning</th></tr>
<tr><td>DTM (terrain)</td><td>Elevations in a raster. <b>Use this raster</b>: a raster of the map. <b>Use map ground surface</b>: the raster that is the ground elevation source of the active map (Contents &gt; Elevation Surfaces &gt; Ground). It must be a raster file; if the ground is a web elevation service the pane says so and tells you what to do. <b>Browse</b>: any raster file. <b>Flat ground</b>: elevation 0 m, terrain ignored.</td></tr>
<tr><td>Vertical unit</td><td>If the raster does not say whether its heights are metres or feet, you are asked (DTM-006).</td></tr>
<tr><td>Show Coverage</td><td>Draws the DTM footprint and the gaps along source-to-receiver paths (red squares) on the map.</td></tr>
<tr><td>Receiver area</td><td>Results exist only inside it; the source may be outside. Four ways: existing polygons (selected or the entire layer), a drawn polygon or rectangle, a radius around the source (follows the source), the captured map extent (fixed).</td></tr>
<tr><td>Receiver grid</td><td>Match the DTM resolution, or a custom cell size in metres. The pane shows the number of cells; a coarse DTM under a fine grid is flagged.</td></tr>
<tr><td>Receiver height</td><td>Metres above the <i>local</i> terrain at every cell, not above sea level.</td></tr></table></div></div>

<h3>5.3 Structures</h3>
<div class="pane">{fig("05_structures.png", "A noise barrier selected in the list.")}<div class="txt">
<table><tr><th>Setting</th><th>Meaning</th></tr>
<tr><td>List entries</td><td>Left tick = <b>Include in Analysis</b> (the engine uses it). &ldquo;Drawn on map&rdquo; = shown in Contents and on the map. The two are independent: hiding an object never changes the calculation, and an excluded object can stay drawn.</td></tr>
<tr><td>Building</td><td>A footprint with a height above ground. Effect in this version: screening (diffraction over the top and around the sides); no reflections. Receiver cells inside the footprint are left empty.</td></tr>
<tr><td>Noise barrier</td><td>A line. Vertical definition: constant height above local terrain, or a fixed absolute top elevation. Gap under the barrier. A profile preview plots the terrain and the barrier top along the line. <b>Transmission</b> is off by default (diffraction only, as in ISO 9613-2); switching it on adds transmission through the barrier from material data and is an engineering approximation.</td></tr>
<tr><td>Edit, Duplicate, Zoom To, Remove</td><td>Remove only takes it out of the scenario; the GIS feature is not touched.</td></tr></table></div></div>
<div class="pane">{fig("05b_enclosure.png", "An enclosure: size, orientation, opening.")}<div class="txt">
<h3 style="margin-top:0">Enclosure (linked to the source)</h3>
<p>Applied <b>once</b>, as a reduction of the radiated sound power (diffuse-field model in your <code>nb_enclosure.m</code>); it is not also treated as a barrier, and the floor counts as ground. A rectangle is defined by length, width and height, orientation (degrees clockwise from north) and an offset from the source; a drawn footprint works too.</p>
<p><b>Opening area (m&sup2;)</b> matters: with no opening the model predicts an unrealistically large reduction (about 50 dB for 25 kg/m&sup2;). A real enclosure has doors, vents and leaks; a message (ENC-021) states the reduction limit that the opening gives. Treat enclosure results as an upper-end estimate.</p>
<p><b>Separate materials for walls and roof</b>: each face gets its own material; the enclosure is combined by area.</p></div></div>
<div class="pane">{fig("05c_material.png", "Material of an enclosure face.")}<div class="txt">
<h3 style="margin-top:0">Material: mass law or manufacturer data</h3>
<ul><li><b>Mass Law</b>: surface density (kg/m&sup2;) or thickness and volumetric density for homogeneous solid layers; the engine computes TL from the limp mass law (<code>nb_material</code>). &ldquo;Show TL per band&rdquo; asks the core and shows the numbers.</li>
<li><b>Manufacturer Data</b>: a TL table (dB) per octave band.</li>
<li><b>Interior absorption coefficient &alpha;</b> (0 to 1) is a different quantity from TL (dB). &alpha; sets the interior sound level; TL sets how much passes through. They are entered and used separately.</li></ul></div></div>

<h3>5.4 Propagation</h3>
<div class="pane">{fig("06_propagation.png", "Propagation section.")}<div class="txt">
<table><tr><th>Setting</th><th>Meaning</th></tr>
<tr><td>Prediction mode</td><td>Shows the ISO edition used: <b>ISO 9613-2:2024</b> (default), the draft amendment (not a published edition) or ISO 9613-2:1996 (superseded).</td></tr>
<tr><td>Ground factor G</td><td>0 = hard (water, concrete), 1 = porous (grass, soil), default 0.5. Advanced: separate G for the source, middle and receiver regions.</td></tr>
<tr><td>Atmosphere</td><td>Temperature (&deg;C), relative humidity (%), pressure (kPa). &ldquo;Show absorption&rdquo; asks the core for the absorption coefficient per band (dB/km) so you can see them.</td></tr>
<tr><td>Terrain screening</td><td>With a DTM the engine always includes terrain diffraction in this version; switching it off is reported as an error (DTM-016) instead of being ignored.</td></tr>
<tr><td>Meteorology</td><td>Favourable propagation (no correction, the default) or long-term average with C<sub>met</sub> from C0 (dB, practical range 0 to about 5).</td></tr>
<tr><td>Active effects</td><td>A plain-language list of the attenuation terms in the current run, e.g. &ldquo;screening by 1 building(s) and 1 barrier(s) (Abar)&rdquo;.</td></tr></table></div></div>

<h3>5.5 Outputs</h3>
<div class="pane">{fig("07_outputs.png", "Outputs section (top).")}<div class="txt">
<table><tr><th>Setting</th><th>Meaning</th></tr>
<tr><td>Output geodatabase</td><td>A file geodatabase (.gdb). Doubled or forward slashes in the path are tolerated.</td></tr>
<tr><td>Run name</td><td>Prefixes every dataset; the pane lists the names that will be created. A name that exists is made unique (<code>_2</code>, <code>_3</code>). Each run saves a <code>_Snapshot</code> table with the whole scenario and the code that ran.</td></tr>
<tr><td>Rasters</td><td>Independent choices: overall A-weighted LAeq, overall unweighted level (energy sum of the 8 bands), and any octave-band rasters. All eight bands always enter the overall results.</td></tr>
<tr><td>Allowed levels</td><td>Section 6.</td></tr>
<tr><td>Shared colour scale</td><td>One minimum and maximum (dB) so baseline and mitigation runs have identical colours.</td></tr>
<tr><td>Detail cells</td><td>None, Levels only, or Full: one invisible polygon per cell; click it with Identify to read every band and every attenuation term (Adiv, Aatm, Agr, Abar).</td></tr>
<tr><td>Add results to the map</td><td>Creates a named group in Contents. Datasets are always written to the geodatabase.</td></tr>
<tr><td>MATLAB engine</td><td>Section 10.</td></tr></table></div></div>

<h3>5.6 Issues</h3>
{fig("08_issues.png", "The Issues list after Preview. Click one to jump to the input that needs attention.", "46%")}
<p>Errors stop the run. Warnings tell you about something that may not be what you meant (for example: reflections from structures are not calculated; the DTM cell is coarser than the output grid). Notes explain what will happen (which datasets will be created, how the pass rule works).</p>

<h2 class="pb">6. Allowed levels: overall and per octave band</h2>
<p>You can define the allowed level in any combination:</p>
<ol><li>an <b>overall limit</b> on LAeq in dB(A);</li><li>a <b>limit for each octave band</b> (63 to 8000 Hz), compared as A-weighted levels (dB(A), the default) or as unweighted levels (dB). Leave a band empty for no limit in that band.</li></ol>
<div class="box"><b>The rule: a cell passes only if every limit you defined is met.</b> If at least one band exceeds its limit, or the overall level exceeds its limit, the cell FAILS. The pane states the rule with your numbers, for example &ldquo;A cell PASSES only if every limit is met: LAeq &lt;= 55 dB(A); 500 Hz &lt;= 45 dB(A). One exceeded band is enough to FAIL.&rdquo;</div>
{fig("07b_limits.png", "Allowed levels: overall limit, the per-band table (here only 500 Hz is limited) and the comparison weighting.", "42%")}
<table><tr><th>Dataset</th><th>Content</th></tr>
<tr><td><code>&lt;run&gt;_PassFail</code></td><td>1 = PASS, 0 = FAIL, with a Status column in its attribute table.</td></tr>
<tr><td><code>&lt;run&gt;_Margin</code></td><td>The <b>largest exceedance over all limits</b> in dB: positive means the cell fails by that much; the most negative values are the cells with the most room.</td></tr>
<tr><td>Detail cells</td><td><code>Status</code>, <code>Margin_dBA</code>, <code>Worst_Hz</code> (the band that exceeds most), <code>Worst_dB</code>, and one <code>Marg_&lt;Hz&gt;</code> field per limited band.</td></tr>
<tr><td><code>&lt;run&gt;_Summary</code></td><td>Each limit, the pass rule, the area failing in m&sup2; and %, and for each limited band the number of cells that exceed it.</td></tr></table>
<p>Tested: the cells that fail are exactly those where LAeq exceeds the overall limit <i>or</i> a band exceeds its limit; <code>Marg_500</code> equals the band level minus its limit to 0.0 dB; weighting &ldquo;unweighted&rdquo; compares the unweighted band level (tests/test_limits.py, 20 checks).</p>

<h2>7. Objects you create appear in Contents</h2>
<p>Whatever you create with a tool or from a layer is a <b>real object</b>, not a temporary drawing. It is written to the feature classes of the file geodatabase <code>NoiseBox_inputs.gdb</code> (in your project folder) and appears in Contents in the group <b>NoiseBox inputs</b>, drawn on the map:</p>
<table><tr><th>Layer</th><th>Shape</th><th>Created by</th><th>Fields</th></tr>
<tr><td>NoiseBox source</td><td>point</td><td>Location menu (layer, coordinates, place on map)</td><td>Name, Height_m</td></tr>
<tr><td>NoiseBox noise barriers</td><td>line</td><td>Barrier menu, sketch or precise placement</td><td>Name, Height_m, Include, Note</td></tr>
<tr><td>NoiseBox buildings</td><td>polygon</td><td>Building menu</td><td>Name, Height_m, Include</td></tr>
<tr><td>NoiseBox enclosures</td><td>polygon</td><td>Enclosure menu</td><td>Name, Height_m, Include</td></tr>
<tr><td>NoiseBox receiver area</td><td>polygon</td><td>Area menu</td><td>Name, Note (mode)</td></tr></table>
<p>The scenario file stays the master: the layers are rebuilt from it after every change, so they never drift away from what the calculation will use. You can select, label, symbolise and zoom to them like any layer. An object whose <i>Drawn on map</i> box is unticked is not written to its layer (it is still calculated if <i>Include</i> is ticked). To change an object, edit it in the pane; to use your own features instead, use the &ldquo;From Layer&rdquo; items. The sync writes in the analysis coordinate system and orients polygons correctly; the log of problems is <code>%LOCALAPPDATA%\\NoiseBox\\addin.log</code>.</p>

<h2 class="pb">8. Worked example: a drill rig behind a 4 m barrier</h2>
<p><b>The question:</b> a drill rig (Lw 92, 96, 98, 97, 94, 90, 85, 78 dB from 63 to 8000 Hz) works at the Israeli TM Grid position 180000 / 665000, 1.2 m above ground. The allowed level is 55 dB(A) overall and, in addition, 45 dB(A) in the 500 Hz band. A 4 m high screen 25 m east of the rig is proposed. How much does it help, and where is the limit still exceeded?</p>
<p>The steps below were run in ArcGIS Pro; every picture is a screenshot of that run. The terrain is the <b>ground surface of the map</b> (SRTM-based FABDEM, 30 m).</p>
{step(1, "New scenario and name", "Click <b>New</b>. The pane opens with the Scenario section. Name it <i>Drill rig example</i>.")}
{fig("02_pane_new.png", "A new scenario.", "86%")}
{step(2, "Source", "In <b>Source</b>: name <i>Drill-01</i>; coordinate system 2039, Easting 180000, Northing 665000, <b>Set source</b> (or <i>Location &gt; Place on Map</i> and click); height 1.2 m; the spectrum in the Lw table. The pane confirms &ldquo;Source placed at 180000, 665000 (EPSG 2039)&rdquo;. The source also appears in Contents as <i>NoiseBox source</i>.")}
{fig("03_source.png", "Source entered by coordinates.", "40%")}
{step(3, "Terrain and receiver area", "In <b>Terrain and Area</b>: <b>Use map ground surface</b> (the pane reports the raster, its 30.9 m cells and its coordinate system; confirm the vertical unit, metres). Draw the receiver area with <i>Area &gt; Draw Rectangle</i> (here 300 m &times; 200 m around the rig). Choose a custom cell size of 10 m and a receiver height of 1.5 m: 30 &times; 20 = 600 cells.")}
{fig("04_terrain.png", "DTM from the map's ground surface.", "40%")}
{step(4, "The barrier", "<b>Barrier &gt; Sketch on Map</b>: click the two ends of the screen. It appears in the list and in Contents (<i>NoiseBox noise barriers</i>). Name it <i>Screen 4 m</i>, vertical definition <i>constant height above local terrain</i>, 4 m. <b>Profile preview</b> shows the terrain and the barrier top along its line.")}
{fig("05_structures.png", "The barrier in the Structures section.", "40%")}
{step(5, "Propagation", "Keep the defaults: ISO 9613-2:2024, G = 0.5, 15 &deg;C, 70 % RH, favourable propagation. The &ldquo;Active effects&rdquo; line lists what the run will include.")}
{step(6, "Outputs and allowed levels", "Choose an output geodatabase, run name <i>B_barrier</i>, overall limit 55 dB(A) and a 500 Hz band limit of 45 dB(A) (A-weighted). The pane repeats the rule.")}
<div class="two"><div>{fig("07_outputs.png", "Output settings.")}</div><div>{fig("07b_limits.png", "The two limits and the pass rule.")}</div></div>
{step(7, "Preview", "Press <b>Preview</b> (or the ribbon button). No acoustics are calculated; the pane lists the issues and the map shows the receiver area, the source and the barrier. Fix every error; read the warnings. Here: 0 errors, and warnings that reflections are not calculated and that the 30.9 m DTM is coarser than the 10 m grid.")}
{fig("09_preview_map.png", "After Preview: inputs on the map (NoiseBox inputs in Contents) and the issue summary.", "92%")}
{step(8, "Run (with the barrier)", "Press <b>Run</b>. The first run starts MATLAB (about 10 s on this computer); the status line shows progress. When it finishes, the results are in Contents in the group <i>NoiseBox: Drill rig example | B_barrier</i>.")}
{fig("10_results_B.png", "Results of run B on the map; the screen's shadow is visible east of the rig.", "92%")}
{step(9, "Baseline for comparison", "Untick <i>Include in Analysis</i> for the screen (it stays drawn), change the run name to <i>A_baseline</i>, run again. Same scenario, no barrier: this is the reference.")}
{fig("12_results_A.png", "Run A (no barrier) in the same window.", "92%")}
{step(10, "Compare", "Numbers from the two runs on the same 600 cells (full detail in the <code>_Summary</code> tables):")}
<table><tr><th>&nbsp;</th><th>A: no barrier</th><th>B: 4 m barrier</th></tr>
<tr><td>LAeq minimum / mean / maximum, dB(A)</td><td>{fnum(A.get('min'))} / {fnum(A.get('mean'))} / {fnum(A.get('max'))}</td><td>{fnum(B.get('min'))} / {fnum(B.get('mean'))} / {fnum(B.get('max'))}</td></tr>
<tr><td>Cells above 55 dB(A)</td><td>{fnum(NUM.get('share_above_55_A'))} %</td><td>{fnum(NUM.get('share_above_55_B'))} %</td></tr>
<tr><td>Area failing at least one limit (overall 55 dB(A) or 500 Hz 45 dB(A))</td><td>{fnum(sA.get('Share of area failing'))} %</td><td>{fnum(sB.get('Share of area failing'))} %</td></tr>
<tr><td>Cells exceeding the 500 Hz limit</td><td>{fnum(sA.get('Cells exceeding the 500 Hz limit'), 0)}</td><td>{fnum(sB.get('Cells exceeding the 500 Hz limit'), 0)}</td></tr></table>
{fig("fig_compare.png", "LAeq without and with the barrier, and the difference (B minus A). The black contour is 55 dB(A). Drawn from the real rasters of the two runs.")}
{fig("fig_passfail.png", "Run B: PASS/FAIL (every limit must be met) and the margin to the nearest limit.", "80%")}
<div class="box"><b>Reading it.</b> The screen lowers levels in its shadow by up to {fnum(abs(NUM.get('largest_reduction_dB', 0)))} dB on this grid, but cells close to the rig and in front of the screen are unchanged. With the 500 Hz limit added, some cells still fail even where the overall level is under 55 dB(A): that is the &ldquo;one exceeded band is enough&rdquo; rule at work, and the Margin raster shows by how much. This is a <b>prediction with the stated simplifications</b> (section 12), not a guarantee.</div>
{step(11, "Look at one cell", "Run again with <i>Detail cells = Full</i> and click a cell with <b>Identify</b>: the level in each band, the dominant source, the distance, the ground elevation and the attenuation terms for that cell, plus <code>Status</code>, <code>Worst_Hz</code> and <code>Marg_500</code>.")}
{step(12, "Save", "<b>Save</b> writes the scenario file. Every run also keeps its own <code>_Snapshot</code> table, so any result can be reproduced later.")}

<h2 class="pb">9. Reading the results</h2>
<table><tr><th>Dataset (prefix = run name)</th><th>Content</th></tr>
<tr><td>_LAeq</td><td>Overall A-weighted level, dB(A), one value per receiver cell (NoData outside the area, inside buildings, at the source, outside the DTM).</td></tr>
<tr><td>_LZ</td><td>Overall unweighted level (energy sum of the 8 bands), if chosen.</td></tr>
<tr><td>_Lp&lt;Hz&gt;</td><td>Octave-band level, dB, for the bands you chose.</td></tr>
<tr><td>_Margin, _PassFail</td><td>Section 6. Created whenever any limit is defined.</td></tr>
<tr><td>_Cells</td><td>Detail polygons (Identify). Fields include LAeq, Status, Lp_/LpA_ per band, DomSrc, Dist_m, Ground_m, PathType, Adiv_/Aatm_/Agr_/Abar_ per band.</td></tr>
<tr><td>_Summary</td><td>Cells, cell size, receiver height, LAeq min/max, the active effects, every limit and the share of area failing.</td></tr>
<tr><td>_Snapshot</td><td>The scenario, what was resolved (coordinate system, grid), and which code ran (MATLAB version, md5 of every <code>.m</code> file). Re-running a snapshot reproduces the raster.</td></tr></table>

<h2>10. Speed: the MATLAB engine</h2>
<p>Starting MATLAB takes about 7 s here and 10 to 80 s on other computers. NoiseBox therefore keeps <b>one MATLAB ready</b> after the first run (mode <i>warm</i>, the default): later runs skip the start-up (in the test: 4.5 s against 12.2 s for a fresh MATLAB on a 60-cell case). Before every run the md5 of every <code>.m</code> file is compared with the previous run; if one changed, MATLAB's function cache is cleared, so <b>an edited <code>.m</code> file still takes effect on the next run</b>. The engine quits after 30 idle minutes. <b>Outputs &gt; MATLAB engine</b> shows its state and has a <b>Stop engine</b> button that frees the memory (about 0.5 GB).</p>
<p>To go back to one MATLAB per run, put <code>{{"engine": "fresh"}}</code> in <code>config.json</code>; <code>docs\\ENGINE_OPTIONS.md</code> records the options that were considered (including why compiling the core to Python was not possible with the licence available here) so you can decide later. The warm and the fresh mode give identical rasters (difference 0.0 dB).</p>

<h2>11. Errors and warnings</h2>
<p>There are {len(I.CATALOGUE)} numbered messages (Appendix A): <b>errors</b> stop the run, <b>warnings</b> allow it but tell you about something that may not be what you intended, <b>notes</b> explain. Each is built from a template that fills in your values, and has a section so a click takes you to the input. Typical examples:</p>
<table><tr><th>Code</th><th>Message</th></tr>
<tr><td>SRC-001</td><td>No source has been placed. &rarr; Use Source &gt; Set Location: From Layer, Enter Coordinates or Place on Map.</td></tr>
<tr><td>SPC-002</td><td>Sound power Lw is missing in 1 band(s): 125 Hz. A missing value is not the same as 0 dB. &rarr; Enter it or load a profile.</td></tr>
<tr><td>DTM-006</td><td>The vertical unit of the DTM is unknown. &rarr; Choose metres or feet for the DTM.</td></tr>
<tr><td>OUT-021</td><td>The limit for 500 Hz is not a number (got x). &rarr; Enter the allowed level in dB, or leave the box empty for no limit in that band.</td></tr>
<tr><td>OUT-023</td><td>(note) A cell passes only if EVERY limit is met: LAeq &lt;= 55 dB(A); 500 Hz &lt;= 45 dB(A). &rarr; One exceeded band is enough to fail; the Margin raster shows the largest exceedance in dB.</td></tr>
<tr><td>ENC-021</td><td>(warning) Enclosure 'Enclosure': openings of 0.50 m2 limit the achievable reduction to 22.0 dB. &rarr; Close or attenuate the openings (silencers) to get more reduction.</td></tr></table>

<h2>12. What the engine calculates and what it does not</h2>
<table><tr><th>Included</th><th>Not included (and what NoiseBox does about it)</th></tr>
<tr><td>Geometric divergence, atmospheric absorption, ground effect (Agr), screening by barriers, buildings and terrain (Abar), an optional C<sub>met</sub>; energy sums over bands and sources; A-weighting; enclosure reduction applied once to the radiated Lw.</td>
<td>Reflections from structures (warning). Angle-dependent directivity (the heading is stored, a message says it is unused). Terrain screening off while keeping a DTM (error DTM-016). Receivers inside a building footprint are left empty. The enclosure model is idealised and needs an opening area.</td></tr></table>
<div class="box warn">No ISO certification or conformance is claimed. The acoustic physics are the user's <code>matlab/core</code> code; NoiseBox prepares the data, runs it, and writes the results.</div>

<h2 class="pb">13. What was tested, and what was not</h2>
<h3>Automated tests (propy, on the development computer)</h3>
<table><tr><th>Test</th><th>Result</th></tr>{tests_html}</table>
<h3>Run inside ArcGIS Pro 3.5.3 (this manual's screenshots)</h3>
<ul><li>Installing the <code>.esriAddinX</code>, the tab and all its buttons, the pane, the menus, opening a scenario, typing values, Preview, Run through MATLAB, results in Contents, a baseline run with the barrier excluded, the real objects in <i>NoiseBox inputs</i>, the DTM from the map's ground surface, the per-band limits.</li>
<li>Source, area, buildings, barriers and enclosures were created through the same pane methods the map tools call after a sketch (an automated test hook, off unless an environment variable is set), because the automated test cannot take over the mouse; the tools' own click handling was reviewed in code and <b>not</b> clicked by a person in this test.</li></ul>
<div class="box warn"><b>Not tested:</b> a person sketching with each map tool; the import window; the enclosure and building results inside Pro (the engine tests cover them); MATLAB versions other than R2023a; computers other than this one; scenes versus 2D maps beyond the 3D scene used here; very large grids.</div>

<h2>14. Troubleshooting</h2>
<table><tr><th>Symptom</th><th>Cause and what to do</th></tr>
<tr><td>No NoiseBox tab</td><td><i>Project &gt; Add-In Manager</i> shows load errors. Install again (section 3). Pro must be closed while installing.</td></tr>
<tr><td>A ribbon button turns grey after a click</td><td>Its handler threw an exception. Read <code>%LOCALAPPDATA%\\NoiseBox\\addin.log</code> (every exception inside the add-in is written there) and report it.</td></tr>
<tr><td>I rebuilt the add-in but Pro shows the old one</td><td>Raise <code>version</code> in <code>Config.daml</code>. If a Pro process that crashed earlier is still listed in Task Manager it keeps the cached DLL open; rename <code>%LOCALAPPDATA%\\ESRI\\ArcGISPro\\AssemblyCache\\{{6B0C3A2E-4D52-4E0B-9B52-0F7B8C1E5A11}}\\NoiseBoxAddin.dll</code> and install again, or restart the computer.</td></tr>
<tr><td>&ldquo;Failed to add data&rdquo; for the results</td><td>The geodatabase path was malformed (doubled backslashes). NoiseBox now normalises it, and if Pro still refuses inside the tool the add-in adds the result layers itself.</td></tr>
<tr><td>The run is slow to start</td><td>The first run starts MATLAB; later runs reuse it (section 10).</td></tr>
<tr><td>The MATLAB link check fails</td><td>Run <code>setup\\setup_noisebox.ps1</code> again; check that MATLAB is licensed for this user; see <code>%LOCALAPPDATA%\\NoiseBox\\engine.log</code>.</td></tr>
<tr><td>Pro asks to recover the project</td><td>It happens after Pro was closed by force. Answer No if you have no unsaved work.</td></tr></table>

<h2 class="pb">Appendix A: every error, warning and note</h2>
{catalogue_html()}

<h2 class="pb">Appendix B: scenario file, command line, configuration</h2>
<p>A scenario is one JSON file (<code>noisebox.scenario/1</code>): <code>source</code> (position in the coordinate system it was entered in, height, spectrum, directivity), <code>terrain</code> (DTM, vertical unit), <code>area</code>, <code>structures</code>, <code>propagation</code>, <code>outputs</code> (including <code>limit_dba</code>, <code>limit_bands</code> and <code>limit_band_weighting</code>). A band that is <code>null</code> is missing. Scenario files written before the per-band limits existed open unchanged.</p>
<pre>propy noisebox_cli.py validate scenario.nbscenario.json
propy noisebox_cli.py preview  scenario.nbscenario.json
propy noisebox_cli.py run      scenario.nbscenario.json
propy noisebox_cli.py engine   status | start | stop
propy tests\\run_all.py &lt;output folder&gt;     (all tests; MATLAB tests take about 40 minutes)</pre>
<p><code>config.json</code> in the NoiseBox folder: <code>{{"python310": "...\\\\python.exe", "engine": "warm", "engine_idle_minutes": 30}}</code>. Environment variables: <code>NOISEBOX_PY310</code>, <code>NOISEBOX_ENGINE</code>, <code>NOISEBOX_HOME</code>.</p>
<p><b>Test hook (developers).</b> If <code>NOISEBOX_AUTOMATION=1</code> is set when ArcGIS Pro starts, JSON command files in <code>%LOCALAPPDATA%\\NoiseBox\\automation</code> can place the source, add structures, set values and zoom, exactly as the tools' finished sketches do. It is off for normal use.</p>
"""

html_doc = "<!doctype html><html><head><meta charset='utf-8'><title>NoiseBox for ArcGIS Pro: manual</title><style>%s</style></head><body>%s</body></html>" % (css, body)
out_html = os.path.join(HERE, "NoiseBox_Manual.html")
with open(out_html, "w", encoding="utf-8") as f:
    f.write(html_doc)
pdf = os.path.join(HERE, "NoiseBox_Manual.pdf")
edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.isfile(edge):
    edge = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
subprocess.run([edge, "--headless", "--disable-gpu", "--no-pdf-header-footer", "--print-to-pdf=" + pdf, "file:///" + out_html.replace("\\", "/")],
               check=True, capture_output=True, timeout=300)
print("written", pdf, os.path.getsize(pdf))
