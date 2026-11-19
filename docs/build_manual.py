"""Builds docs/NoiseBox_Manual.html and the PDF (Edge headless print). Run with propy after make_manual_figures.py and
make_schematics.py:   propy docs\\build_manual.py"""
import html
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from noisebox import issues as I  # noqa: E402

FIG = json.load(open(os.path.join(HERE, "figures", "figures.json"), encoding="utf-8"))
TS = {}
if os.path.isfile(os.path.join(HERE, "test_summary.json")):
    TS = json.load(open(os.path.join(HERE, "test_summary.json"), encoding="utf-8"))

SECTION_NAMES = {"SCN": "Scenario file and coordinate system", "SRC": "Source location and height", "SPC": "Source spectrum",
                 "DIR": "Directivity", "DTM": "Terrain (DTM)", "ARA": "Receiver area and grid", "STR": "Structures (general)",
                 "BLD": "Buildings", "BAR": "Noise barriers", "ENC": "Enclosures", "PRP": "Propagation settings",
                 "OUT": "Outputs", "ENG": "Engine and run"}


def esc(s):
    return html.escape(str(s))


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


def table_rows():
    return "".join("<tr><td>%s</td><td>%.1f</td><td>%.1f</td><td>%.1f</td></tr>" % (r["name"], r["A"], r["B"], r["C"]) for r in FIG["table"])


css = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', Arial, sans-serif; color: #1c2430; font-size: 10.3pt; line-height: 1.45; }
h1 { font-size: 27pt; color: #1f3b5c; margin: 0 0 4pt 0; }
h2 { font-size: 16pt; color: #1f3b5c; border-bottom: 2px solid #2f6fa8; padding-bottom: 3pt; margin-top: 22pt; page-break-after: avoid; }
h3 { font-size: 12pt; color: #2f6fa8; margin: 14pt 0 4pt; page-break-after: avoid; }
.cover { height: 250mm; display: flex; flex-direction: column; justify-content: center; page-break-after: always; }
.cover .sub { font-size: 14pt; color: #4b5563; margin-bottom: 26pt; }
.cover .meta { color: #6b7280; font-size: 10pt; border-top: 1px solid #d1d5db; padding-top: 8pt; margin-top: 26pt; }
.pb { page-break-before: always; }
.box { border-left: 4px solid #2f6fa8; background: #eef4fb; padding: 7pt 10pt; margin: 8pt 0; page-break-inside: avoid; }
.warn { border-left-color: #d9822b; background: #fff6ea; }
.bad { border-left-color: #b42318; background: #fdecea; }
.ok { border-left-color: #2e7d32; background: #edf7ee; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0; font-size: 9.4pt; page-break-inside: auto; }
th { background: #1f3b5c; color: white; text-align: left; padding: 4pt 6pt; }
td { border-bottom: 1px solid #e5e7eb; padding: 3.5pt 6pt; vertical-align: top; }
tr { page-break-inside: avoid; }
table.cat { font-size: 7.6pt; } table.cat td { padding: 2pt 4pt; }
table.cat tr.error td:nth-child(2) { color: #b42318; font-weight: 600; }
table.cat tr.warning td:nth-child(2) { color: #b26200; font-weight: 600; }
table.cat tr.info td:nth-child(2) { color: #6b7280; }
.step { display: flex; gap: 9pt; margin: 9pt 0; page-break-inside: avoid; }
.num { flex: 0 0 22pt; height: 22pt; border-radius: 50%; background: #2f6fa8; color: white; text-align: center; line-height: 22pt; font-weight: 700; }
.step .body { flex: 1; }
.fig { text-align: center; margin: 8pt 0; page-break-inside: avoid; }
.fig img { max-width: 100%; }
.cap { font-size: 8.6pt; color: #6b7280; margin-top: 2pt; }
.two { display: flex; gap: 12pt; align-items: flex-start; } .two > div { flex: 1; }
code, .k { font-family: Consolas, monospace; background: #f1f3f5; padding: 0 3pt; border-radius: 2pt; font-size: 9.2pt; }
pre { background: #f1f3f5; padding: 7pt 9pt; border-radius: 4pt; font-size: 8.8pt; overflow: hidden; white-space: pre-wrap; }
.toc a { color: #1f3b5c; text-decoration: none; } .toc li { margin: 2pt 0; }
.yes { color: #2e7d32; font-weight: 600; } .no { color: #b42318; font-weight: 600; } .part { color: #b26200; font-weight: 600; }
ul, ol { margin: 4pt 0 4pt 18pt; padding: 0; }
"""

tests = [[a, b.replace(": 1 checks passed, 0 failed", ": overall result PASS")] for a, b in TS.get("lines", [])]
tests_html = "".join("<tr><td>%s</td><td>%s</td></tr>" % (esc(a), esc(b)) for a, b in tests)

body = f"""
<div class="cover">
  <h1>NoiseBox for ArcGIS Pro</h1>
  <div class="sub">User manual: outdoor noise mapping to ISO 9613-2, with a worked example</div>
  <div class="box warn"><b>Status of this version.</b> The calculation engine, the scenario files, the checks and the Python tools are built and tested
  (section 9). The ribbon tab and dockable pane (the <i>add-in</i>) are <b>compiled and packaged</b> (<code>dist\\NoiseBox.esriAddinX</code>) and pass static checks
  (Esri's DAML schema, class names, XAML bindings), but they have <b>never been loaded or clicked in ArcGIS Pro</b>: no automated way to drive Pro's window was available.
  Pictures of the ribbon and pane in this manual are therefore <b>schematic drawings</b> made from the design, not screenshots. Every map, chart and number in the
  worked example is <b>real output</b> of the engine. Please report anything that behaves differently from this manual when you first use the ribbon.</div>
  <div class="meta">ArcGIS Pro 3.5 or later &nbsp;|&nbsp; MATLAB R2022b to R2024b (tested: R2023a) &nbsp;|&nbsp; Python 3.10 for the MATLAB link<br>
  Prediction method: ISO 9613-2:2024 (default), draft amendment and 1996 edition selectable &nbsp;|&nbsp; No ISO certification or conformance is claimed.</div>
</div>

<h2 style="margin-top:0">Contents</h2>
<ol class="toc">
<li>What NoiseBox does</li><li>What you need</li><li>Installing on a computer</li><li>The workspace: ribbon and pane</li>
<li>Worked example: a drill rig, step by step</li><li>Reading the results</li><li>Errors and warnings</li>
<li>What the engine calculates and what it does not</li><li>What was tested, and what was not</li><li>Troubleshooting</li>
<li>Appendix A: every error, warning and note</li><li>Appendix B: scenario file and command line</li></ol>

<h2>1. What NoiseBox does</h2>
<p>NoiseBox predicts the sound level of a point source at every cell of a grid, the way ISO 9613-2 describes it, and puts the result on your map. You describe a
<b>scenario</b> (a source and its spectrum, terrain, an area, and optionally buildings, noise barriers and an enclosure around the source). NoiseBox checks it,
calculates it in your own validated MATLAB code, and adds a named group of rasters to <i>Contents</i>. You can then change one thing (a taller barrier, an enclosure)
and compare.</p>
<div class="two"><div>
<h3>Why the checking is built in</h3>
<p>Every input is checked before anything runs. A problem is shown as a numbered message that says what is wrong, <i>why</i> it matters, and what to do. Clicking a message takes you to the input. There are {len(I.CATALOGUE)} such messages (Appendix A).</p></div>
<div><h3>How the pieces fit</h3>
<p>ArcGIS Pro (ribbon + pane) writes a <b>scenario file</b>. Pro's Python reads it and starts a small <b>worker</b> in Python 3.10 that owns MATLAB. MATLAB runs your <code>matlab\\core</code> files. No acoustics are calculated anywhere else, so editing a <code>.m</code> file changes the next run.</p></div></div>
<h3>Two ways to use it</h3>
<table><tr><th>Way</th><th>For</th><th>Status</th></tr>
<tr><td><b>Ribbon tab + pane</b> (the add-in)</td><td>Interactive: pick or draw the source, structures and area on the map, see them update, run, compare.</td><td class="part">Compiled, packaged, statically checked; not yet run inside Pro</td></tr>
<tr><td><b>Toolbox <code>NoiseBox.pyt</code></b> (6 tools incl. <i>Run Scenario</i>)</td><td>Dialog tools, scripts, batch runs and saved scenario files. Same engine.</td><td class="yes">Built and tested</td></tr></table>

<h2 class="pb">2. What you need</h2>
<table><tr><th>Item</th><th>Version</th><th>Notes</th></tr>
<tr><td>ArcGIS Pro</td><td>3.5 or later</td><td>Tested with 3.5.3 (Python 3.11 inside Pro).</td></tr>
<tr><td>MATLAB</td><td>R2022b to R2024b</td><td>Licensed on that computer. Tested with R2023a. No toolboxes are used.</td></tr>
<tr><td>Python 3.10 (64-bit)</td><td>3.10.x</td><td>From python.org. Needed only because the MATLAB Engine for Python does not run in Pro's Python 3.11. Used in a separate environment.</td></tr>
<tr><td>This NoiseBox folder</td><td>&nbsp;</td><td>Copy it anywhere (not inside a folder that OneDrive/Dropbox is syncing is best).</td></tr>
<tr><td><i>Only to rebuild the ribbon add-in:</i> .NET SDK</td><td>8 or newer</td><td><code>winget install Microsoft.DotNet.SDK.8</code>. The computer that <i>uses</i> the add-in does not need it.</td></tr>
<tr><td>A DTM raster (optional)</td><td>any single-band elevation raster</td><td>The example uses <code>sample\\dem_sample.tif</code>. For Israel, <code>setup\\make_israel_dem.py</code> downloads SRTM 30 m.</td></tr></table>

<h2>3. Installing on a computer</h2>
<p>Do these once per computer. Everything is relative to the NoiseBox folder, so the folder can be moved or copied.</p>
<div class="step"><div class="num">1</div><div class="body"><b>Copy the folder.</b> Copy the whole <code>noisebox_for_Arc_GIS_pro</code> folder (or clone the GitHub repository) to the new computer, for example <code>C:\\NoiseBox</code>.</div></div>
<div class="step"><div class="num">2</div><div class="body"><b>Install Python 3.10</b> from python.org if <code>py -3.10 --version</code> does not work in a command window. Tick <i>Add to PATH</i> or <i>py launcher</i>.</div></div>
<div class="step"><div class="num">3</div><div class="body"><b>Run the setup script.</b> Open PowerShell in the NoiseBox folder and run
<pre>.\\setup\\setup_noisebox.ps1</pre>
It creates the Python 3.10 environment in <code>%LOCALAPPDATA%\\NoiseBox\\venv310</code>, installs numpy and the MATLAB Engine for Python from your MATLAB installation (add <code>-MatlabRoot "D:\\MATLAB\\R2023a"</code> if MATLAB is not in <code>C:\\Program Files\\MATLAB</code>), and registers the folder for the add-in.</div></div>
<div class="step"><div class="num">4</div><div class="body"><b>Add the toolbox in ArcGIS Pro.</b> <i>Catalog pane &gt; Toolboxes &gt; right-click &gt; Add Toolbox</i>, choose <code>NoiseBox.pyt</code>. Run <b>4. Utilities &gt; Check MATLAB Link</b>. Expected: <i>MATLAB link OK</i>, a smoke-test level of about 45.22 dB(A) and matching <code>.m</code> file hashes. This step proves the whole chain works on this computer.</div></div>
<div class="step"><div class="num">5</div><div class="body"><b>(Ribbon add-in) Get the package.</b> The repository already contains the built package <code>dist\\NoiseBox.esriAddinX</code>; you can skip to step 6. To rebuild it (after changing the source), on a computer with a .NET SDK (8 or newer; built here with 11.0.100, <code>winget install Microsoft.DotNet.SDK.8</code>) and ArcGIS Pro 3.5:
<pre>.\\setup\\build_addin.ps1</pre>
The script builds <code>addin\\NoiseBoxAddin</code> and zips <code>Config.daml</code> and the assembly into <code>dist\\NoiseBox.esriAddinX</code>. (Esri's own packaging step needs Visual Studio's MSBuild, so the script packages the add-in itself, in the same layout.) The computer that only <i>uses</i> the add-in needs neither the SDK nor Visual Studio.</div></div>
<div class="step"><div class="num">6</div><div class="body"><b>Install the add-in.</b> Close ArcGIS Pro, double-click <code>NoiseBox.esriAddinX</code>, choose <i>Install</i>. Start Pro and open a map: a <b>NoiseBox</b> tab appears. (If Pro asks, allow add-ins from this file.) The add-in finds the Python side through <code>%LOCALAPPDATA%\\NoiseBox\\addin.json</code>, which step 3 wrote; on a computer where you only copy the <code>.esriAddinX</code>, still run step 3 there, or set the environment variable <code>NOISEBOX_HOME</code> to the NoiseBox folder.</div></div>
<div class="box warn"><b>Step 6 has not been done yet.</b> The package builds and passes the static checks (section 9), but installing it into ArcGIS Pro and clicking through the ribbon has not been tried. If Pro reports an add-in error on first start, send the message shown by <i>Project &gt; Add-In Manager</i>. Steps 1 to 4 (the toolbox route) have been run and tested end to end.</div>

<h2 class="pb">4. The workspace: ribbon and pane</h2>
<p>The map stays in the centre and <i>Contents</i> on the left. NoiseBox adds one ribbon tab and one pane on the right (docked with <i>Catalog</i>).</p>
<div class="fig"><img src="figures/ribbon.png" width="100%"><div class="cap">Schematic of the NoiseBox tab (drawn from the design, not a screenshot): six groups; a &#9662; marks a split button whose arrow offers the alternatives.</div></div>
<table><tr><th>Group</th><th>Buttons</th><th>What it does</th></tr>
<tr><td>Scenario</td><td>New, Open, Save, Duplicate</td><td>A scenario is one file (<code>.nbscenario.json</code>). Duplicate it to try a mitigation next to the baseline.</td></tr>
<tr><td>Source</td><td>Set Location &#9662;, Source Spectrum, Directivity</td><td><i>Set Location</i> arrow: <b>From Layer</b>, <b>Enter Coordinates</b>, <b>Place on Map</b> (activates the placement tool at once; Esc cancels).</td></tr>
<tr><td>Terrain and Area</td><td>Select DTM &#9662;, Set Analysis Area &#9662;, Receiver Grid</td><td>DTM from the project's rasters or browse; area from polygons, drawn polygon or rectangle, radius around the source, or the captured map extent; cell size (match the DTM or custom).</td></tr>
<tr><td>Structures</td><td>Add Building &#9662;, Add Noise Barrier &#9662;, Add Enclosure &#9662;</td><td>From a layer, drawn, or entered numerically (barrier: start, length, azimuth, height; enclosure: length, width, height, orientation).</td></tr>
<tr><td>Propagation</td><td>Ground, Atmosphere, Terrain Screening, Meteorology</td><td>Each opens its section of the pane.</td></tr>
<tr><td>Analysis</td><td>Preview, Run, Results</td><td><b>Preview</b> is fast and calculates no acoustics; <b>Run</b> calculates and adds results to Contents.</td></tr></table>
<h3>The pane</h3>
<p>Sections open and close independently and can be visited in any order. A closed section summarises its real settings (<i>Drill-01, 1.2 m above ground</i>). <b>Preview</b> and <b>Run</b> stay at the bottom. If something is missing, the message names it and clicking it opens the input.</p>
<div class="two"><div class="fig"><img src="figures/pane_source.png" width="100%"><div class="cap">Schematic: Source section open, other sections collapsed with their summaries.</div></div>
<div class="fig"><img src="figures/pane_structures.png" width="100%"><div class="cap">Schematic: Structures. The checkbox is <i>Include in Analysis</i>; <i>Drawn on map</i> only controls the drawing.</div></div></div>

<h2 class="pb">5. Worked example: a drill rig behind a screen</h2>
<p><b>Situation.</b> A drill rig (<i>Drill-01</i>) runs at a site in Tel Aviv (Israeli TM Grid, EPSG 2039). Neighbours stand 60 to 160 m to the east. The limit at their boundary is <b>55 dB(A)</b>. We predict the baseline, then add a 4 m noise barrier, then a sound-proof enclosure around the rig, and see what each buys. The example uses the sample data in <code>sample\\</code>, so you can repeat every step.</p>
<div class="step"><div class="num">1</div><div class="body"><b>Open the map and a new scenario.</b> Open your project and a map. On the NoiseBox tab click <b>New</b>. In the pane, <i>Scenario</i>, type the name <code>Drill rig, baseline</code>.</div></div>
<div class="step"><div class="num">2</div><div class="body"><b>Place the source.</b> Click the arrow beside <b>Set Location</b>. Choose one of three equivalent ways; all give the same point:
<ul><li><b>From Layer:</b> choose <code>sources</code> (from <code>sample\\NoiseBox_sample.gdb</code>), select the point on the map, click <i>Use this layer point</i>. If several points are selected you are asked which one.</li>
<li><b>Enter Coordinates:</b> the coordinate fields open and the first is focused. Choose EPSG 2039; the labels read <i>Easting</i> and <i>Northing</i> (for WGS 84 they would read <i>Longitude</i> and <i>Latitude</i>). Enter <code>180000</code> and <code>665000</code>.</li>
<li><b>Place on Map:</b> the placement tool starts at once; click the map. Coordinates appear in the pane immediately.</li></ul>
Name the source <code>Drill-01</code>. Under <i>Source height above ground</i> enter <code>1.2</code> (metres).</div></div>
<div class="step"><div class="num">3</div><div class="body"><b>Enter the spectrum.</b> In the Lw table type the eight sound power levels, or copy a row or column from Excel or MATLAB and click <b>Paste</b> (or press Ctrl+V in the table): <code>92 96 98 97 94 90 85 78</code> dB re 1 pW for 63 to 8000 Hz. Use <b>Save profile</b> to keep it as <i>Drill rig (example)</i>. An empty cell is <i>missing</i> and stops the run; it is not read as 0 dB.
<div class="fig"><img src="figures/pane_source.png" width="38%" style="display:none"></div></div></div>
<div class="step"><div class="num">4</div><div class="body"><b>Select the terrain.</b> <i>Terrain and Area</i>: choose the raster <code>dem_sample</code> from the list (or Browse) and click <i>Use this raster</i>. The pane shows its native cell size, coordinate system and vertical unit. If the unit is unknown it asks you to choose metres or feet, because a wrong unit would be off by a factor 3.28. <b>Show Coverage</b> draws any gaps in red. The source elevation then appears: ground 21.0 m + height 1.2 m = 22.2 m.</div></div>
<div class="step"><div class="num">5</div><div class="body"><b>Set the analysis area and grid.</b> Click <b>Set Analysis Area &#9662; &gt; Draw Rectangle</b> and drag a rectangle 300 m wide and 200 m high around the source (or enter coordinates in the scenario). Results are produced only inside it; the source may even be outside. Set <b>Custom</b> cell size <code>5</code> m and receiver height <code>1.5</code> m (above the terrain at each receiver cell). The pane shows about <b>{FIG['cells']:,} receiver cells</b>.</div></div>
<div class="step"><div class="num">6</div><div class="body"><b>Outputs.</b> Choose an output geodatabase (a <code>.gdb</code>), the run name <code>A_baseline</code>, tick <i>LAeq dB(A)</i> and <i>unweighted level</i>, tick the 500 and 1000 Hz band rasters, set the allowed level <code>55</code> dB(A) and the shared colour scale <code>35</code> to <code>75</code> dB. The pane lists the dataset names that will be created.</div></div>
<div class="step"><div class="num">7</div><div class="body"><b>Preview, then Run.</b> Click <b>Preview</b>. Anything missing appears in <i>Issues</i> with a specific message, for example:
<div class="fig"><img src="figures/pane_issues.png" width="46%"><div class="cap">Schematic of the Issues section when height and one band are missing. Real texts are in Appendix A.</div></div>
Fix them (click an issue to go to the input), then click <b>Run</b>. MATLAB starts (10 to 80 seconds), then the grid is calculated. When it finishes, the results are in <i>Contents</i> in the group <code>NoiseBox: Drill rig, baseline | A_baseline</code>.</div></div>
<div class="fig"><img src="figures/maps_abc.png" width="100%"><div class="cap">Real output, shared colour scale. A baseline; B with the 4 m barrier; C with barrier and enclosure. The dark line is the 55 dB(A) limit. Red dot: source. {FIG['engine']}, ISO 9613-2:2024.</div></div>
<div class="step"><div class="num">8</div><div class="body"><b>Add the barrier.</b> <b>Duplicate</b> the scenario (name it <code>B_barrier</code>). <b>Add Noise Barrier &#9662; &gt; Precise Placement</b>: click the start point, then in the pane enter length <code>120</code> m, azimuth <code>0</code> (north), height <code>4</code> m. (Azimuth is clockwise from map north.) The barrier on the map moves as you type. Keep <i>Constant height above local terrain</i>. Click <b>Profile preview</b> to check the ground and barrier top:
<div class="fig"><img src="figures/profile.png" width="62%"><div class="cap">Real output: ground from the DTM and the barrier top. The engine uses a flat top per barrier segment ({FIG['flat_top']:.1f} m).</div></div>
The barrier is calculated as <i>diffraction only</i>. (Tick <i>Also calculate transmission</i> only if you can give the material.) Run it.</div></div>
<div class="step"><div class="num">9</div><div class="body"><b>Add the enclosure.</b> Duplicate again (<code>C_barrier_enclosure</code>). <b>Add Enclosure &#9662; &gt; Quick Rectangle</b>: length 6 m, width 4 m, height 3 m, linked to the source. The footprint, roof and source appear on the map. Choose <b>Mass Law</b> and enter surface density <code>25</code> kg/m&sup2;, and the interior absorption coefficient alpha <code>0.3</code> in every band (alpha is a coefficient from 0 to 1, <b>not</b> a dB value). Enter an <b>opening area</b> of <code>0.5</code> m&sup2; (a ventilation opening). <i>Show TL per band</i> asks the core for the transmission loss (an <i>estimate</i>, labelled so).
<div class="box warn"><b>Do not skip the opening.</b> The enclosure model is idealised: a closed 25 kg/m&sup2; box with absorptive walls would give about 50 dB of reduction at high frequencies, which no real enclosure reaches because of openings, leaks, doors and flanking paths. With the 0.5 m&sup2; opening the achievable reduction is limited to about 22 dB (warning ENC-021 says so). Treat enclosure results as an estimate and confirm with measurements.</div> To give each wall and the roof its own material, tick <i>Separate materials</i> and pick a face; the selected face is highlighted on the map. With manufacturer data choose <b>Manufacturer Data</b> and enter measured TL and alpha per band. Run it.
<div class="fig"><img src="figures/spectrum.png" width="62%"><div class="cap">Real output: source Lw and the Lw radiated through the enclosure (diffuse-field model, applied once).</div></div></div></div>
<div class="step"><div class="num">10</div><div class="body"><b>Compare.</b> The three runs now sit in Contents, drawn with the same colours. The difference maps show where each measure helps:
<div class="fig"><img src="figures/differences.png" width="86%"><div class="cap">Real output: reduction in dB from the barrier, and additionally from the enclosure.</div></div>
<table><tr><th>Receiver</th><th>A baseline dB(A)</th><th>B + barrier</th><th>C + barrier + enclosure</th></tr>{table_rows()}
<tr><td><b>Highest level</b></td><td>{FIG['max']['A']:.1f}</td><td>{FIG['max']['B']:.1f}</td><td>{FIG['max']['C']:.1f}</td></tr>
<tr><td><b>Share of cells above 55 dB(A)</b></td><td>{FIG['share_above_55']['A']:.0f} %</td><td>{FIG['share_above_55']['B']:.0f} %</td><td>{FIG['share_above_55']['C']:.0f} %</td></tr></table>
Reading this for a decision: the enclosure removes the exceedance where the barrier alone does not; compare the share above the limit, not only the maximum. A scenario edited later never changes these results: each run keeps a snapshot (section 6).</div></div>

<h2 class="pb">6. Reading the results</h2>
<h3>What appears in Contents</h3>
<pre>NoiseBox: Drill rig, baseline | A_baseline        (one group per run)
  LAeq, dB(A) [iso2024]                          overall A-weighted level, shown first
  Lz unweighted energy sum of 8 bands, dB        optional
  A_baseline | Octave bands (Lp, unweighted)     only the bands you ticked
  A_baseline | Limit check                       margin to the limit, PASS/FAIL (if a limit was given)
  A_baseline | Inspect                           detail cells: click a cell to read every value</pre>
<p>Legends carry the quantity, unit and prediction mode. With a <i>shared colour scale</i> the same colour means the same level in the baseline and in every mitigation run. Names are made unique, so an earlier run is never overwritten.</p>
<h3>Click a cell, read everything</h3>
<p>With <i>Detail cells</i> = Full, use <b>Identify</b> on the map. Each cell lists <code>LAeq</code>, <code>LZ</code>, <code>Status</code> (PASS/FAIL), <code>Margin_dBA</code>, <code>Lp_63 ... Lp_8000</code>, <code>LpA_63 ... LpA_8000</code>, the dominant source, distance, ground elevation, path type (free, blocked, clear crest), and for each band the attenuations <code>Adiv</code>, <code>Aatm</code>, <code>Agr</code>, <code>Abar</code>. The detail check <i>Lp = Lw + Dc - (Adiv + Aatm + Agr + Abar)</i> holds to 1e-12 dB. Above 100 000 cells the detail cells are skipped (and you are told).</p>
<h3>Cells with no value</h3>
<p>Cells inside a building footprint, at the source, outside the DTM or outside the area are left empty (NoData). The run summary counts the cells inside buildings, and a warning gives the share of empty cells.</p>
<h3>Snapshots</h3>
<p>Each run writes a table <code>&lt;run&gt;_Snapshot</code> into the geodatabase: the whole scenario (settings, spectrum, material data, structures), what was resolved, the MATLAB version and the code fingerprint. Re-running a snapshot reproduces the raster exactly (tested to 1e-9 dB). Command: <code>propy noisebox_cli.py snapshot &lt;gdb&gt; &lt;run&gt; --to scenario.json</code>.</p>

<h2>7. Errors and warnings</h2>
<p>There are three kinds. <b>Error:</b> the run is blocked until you fix it. <b>Warning:</b> it runs, but the result may not mean what you expect. <b>Note:</b> explains what will happen (for example that a hidden barrier is still calculated). Each has a code such as <code>SRC-014</code> (prefix = area: SRC source, SPC spectrum, DIR directivity, DTM terrain, ARA area and grid, STR/BLD/BAR/ENC structures, PRP propagation, OUT outputs, ENG engine).</p>
<table><tr><th>You see</th><th>It means</th><th>Do</th></tr>
<tr><td>SRC-014 Source height above ground is missing</td><td>The tool will not guess a height.</td><td>Type the height in metres.</td></tr>
<tr><td>SPC-002 Lw is missing in 1 band(s): 125 Hz</td><td>An empty cell is not 0 dB.</td><td>Fill it, or type 0 if it really is 0.</td></tr>
<tr><td>DTM-006 The vertical unit of the DTM is unknown</td><td>Metres or feet cannot be guessed.</td><td>Choose the unit in the pane.</td></tr>
<tr><td>DTM-008 The source lies outside the DTM coverage</td><td>No ground elevation at the source.</td><td>Choose a larger DTM, or remove it for flat ground.</td></tr>
<tr><td>ENC-004 The source is outside the enclosure footprint</td><td>The enclosure does not contain the source.</td><td>Move one of them.</td></tr>
<tr><td>ENC-010 alpha is missing at 125 Hz</td><td>Interior absorption is needed for the enclosure model.</td><td>Enter alpha (0 to 1) for every band.</td></tr>
<tr><td>BAR-022 transmission without material</td><td>You asked for transmission but gave no TL or mass.</td><td>Enter a material or untick transmission.</td></tr>
<tr><td>OUT-001 / OUT-003 no output geodatabase / not a .gdb</td><td>Rasters need a file geodatabase.</td><td>Choose a <code>.gdb</code>.</td></tr>
<tr><td>DTM-016 terrain screening off is not available</td><td>With a DTM the engine always includes terrain diffraction.</td><td>Leave it on, or remove the DTM.</td></tr></table>
<p>The complete list is Appendix A. Preview shows all issues at once; the same checks run again at the start of Run.</p>

<h2 class="pb">8. What the engine calculates and what it does not</h2>
<table><tr><th>Effect</th><th>In this version</th><th>Notes</th></tr>
<tr><td>Geometric divergence, atmospheric absorption, ground effect</td><td class="yes">Yes</td><td>ISO 9613-2:2024 (default); draft amendment and 1996 edition selectable. Uniform G, or separate source / middle / receiver G.</td></tr>
<tr><td>Terrain: elevations and diffraction from a DTM</td><td class="yes">Yes</td><td>Cannot be switched off while keeping elevations (reported as an error, DTM-016).</td></tr>
<tr><td>Screening by buildings and barriers (top and side paths)</td><td class="yes">Yes</td><td>Where terrain and structures obstruct the same path the engine takes the highest obstruction once; attenuation is not added twice. Barrier top is flat per segment.</td></tr>
<tr><td>Transmission through a barrier</td><td class="part">Optional, approximate</td><td>Energy sum of diffracted and transmitted paths. An engineering approximation, <b>not</b> part of ISO 9613-2.</td></tr>
<tr><td>Source enclosure</td><td class="part">Yes, diffuse-field model</td><td>Reduces the radiated sound power once (EN ISO 15667 style). Panel TL (dB) and interior alpha (0 to 1) are used separately. Assumes a diffuse interior field, no resonance or coincidence effects; the floor is ground. Several surfaces are combined by area (new core file <code>nb_enclosure_surfaces.m</code>; <code>nb_enclosure.m</code> is unchanged).</td></tr>
<tr><td>Constant directivity correction Dc per band</td><td class="yes">Yes</td><td>One value per band for all directions.</td></tr>
<tr><td>Angle-dependent directivity, heading</td><td class="no">No</td><td>The heading is stored but does not change results.</td></tr>
<tr><td>Long-term meteorological correction C_met</td><td class="yes">Yes</td><td>Needs C0; applied to A-weighted levels only. Not applied by default.</td></tr>
<tr><td>Reflections from buildings and barriers</td><td class="no">No</td><td>ISO 9613-2 cl. 7.5 image sources are not implemented.</td></tr>
<tr><td>Multiple sources</td><td class="part">Core yes, ribbon one source</td><td>One source per scenario in the ribbon; the toolbox accepts several.</td></tr></table>

<h2>9. What was tested, and what was not</h2>
<div class="box ok"><b>Checked independently of the Pro window</b> (the calculation tests run the real MATLAB core, R2023a):
<table>{tests_html}</table></div>
<div class="box bad"><b>Not tested:</b> anything that needs the Pro window itself: the ribbon, the pane, the map tools (placing, sketching, picking, heading), the import window, and the add-in install step, which compile and pass static checks but were never run in ArcGIS Pro; Identify clicks on detail cells; the <i>Run Scenario</i> tool inside the Pro window (it was run through ArcPy's geoprocessing framework); the shared colour scale (it uses Pro's raster symbology objects); MATLAB versions other than R2023a; other computers.</div>

<h2>10. Troubleshooting</h2>
<table><tr><th>Problem</th><th>Check</th></tr>
<tr><td>Check MATLAB Link fails: Python 3.10 not found</td><td>Run <code>setup\\setup_noisebox.ps1</code>; or set <code>NOISEBOX_PY310</code> to a <code>python.exe</code>.</td></tr>
<tr><td>"The MATLAB worker ended without a result"</td><td>Open MATLAB once to check the licence and that no other session blocks it; run Check MATLAB Link.</td></tr>
<tr><td>Rasters cannot be saved (error 010240)</td><td>The output must be a file geodatabase (<code>.gdb</code>) that is not locked or read-only.</td></tr>
<tr><td>The add-in says the NoiseBox folder was not found</td><td>Run step 3 on that computer, or set <code>NOISEBOX_HOME</code>.</td></tr>
<tr><td>The run is slow</td><td>About 7 ms per cell after a 10 to 80 s MATLAB start. Use a larger cell size or a smaller area.</td></tr>
<tr><td>You edited a <code>.m</code> file</td><td>Nothing to do: every run starts a fresh MATLAB. Check MATLAB Link shows the new hashes.</td></tr>
<tr><td>After editing <code>noisebox\\*.py</code> or <code>NoiseBox.pyt</code></td><td>Right-click the toolbox &gt; Refresh.</td></tr></table>

<h2 class="pb">Appendix A: every error, warning and note</h2>
<p>{len(I.CATALOGUE)} entries. <span style="color:#b42318"><b>error</b></span> blocks the run; <span style="color:#b26200"><b>warning</b></span> allows it; note explains. Text in braces is replaced by the actual value or name.</p>
{catalogue_html()}

<h2 class="pb">Appendix B: scenario file and command line</h2>
<p>The scenario is plain JSON, schema <code>noisebox.scenario/1</code>; the add-in and the tools read and write the same file. Main parts: <code>source</code> (location, height, spectrum, directivity), <code>terrain</code>, <code>area</code>, <code>structures</code> (buildings, barriers, enclosures, each with <code>include</code> and <code>visible</code>), <code>propagation</code>, <code>outputs</code>.</p>
<pre>propy noisebox_cli.py new   my.nbscenario.json --name "Drill rig"
propy noisebox_cli.py validate my.nbscenario.json          (--fast: no GIS data)
propy noisebox_cli.py preview  my.nbscenario.json          (issues, grid, DTM coverage, faces)
propy noisebox_cli.py run      my.nbscenario.json          (needs the output .gdb)
propy noisebox_cli.py snapshot &lt;gdb&gt; &lt;run&gt; --to earlier.json
propy noisebox_cli.py parse-spectrum --text "92 96 98 97 94 90 85 78"
propy noisebox_cli.py dtm-info &lt;raster&gt;     |  crs 2039  |  suggest-crs 34.78 32.08</pre>
<p>In ArcGIS Pro the same run is available as the tool <b>NoiseBox &gt; 5. Add-in &gt; Run Scenario</b> (one parameter: the scenario file), which adds the grouped, styled results to the open map. The original tools (Noise Map, Noise at Receivers, Compare Noise Maps, Create Input Layers, Check MATLAB Link) are unchanged.</p>
"""

doc = "<!doctype html><html><head><meta charset='utf-8'><title>NoiseBox manual</title><style>%s</style></head><body>%s</body></html>" % (css, body)
hp = os.path.join(HERE, "NoiseBox_Manual.html")
with open(hp, "w", encoding="utf-8") as f:
    f.write(doc)
pdf = os.path.join(HERE, "NoiseBox_Manual.pdf")
edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.isfile(edge):
    edge = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
subprocess.run([edge, "--headless", "--disable-gpu", "--no-pdf-header-footer", "--print-to-pdf=" + pdf,
                "file:///" + hp.replace("\\", "/")], check=True, timeout=180)
print("wrote", pdf, os.path.getsize(pdf))
