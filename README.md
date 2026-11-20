# NoiseBox for ArcGIS Pro

ISO 9613-2 outdoor noise maps inside ArcGIS Pro, built as a Python toolbox (`NoiseBox.pyt`).
**All acoustics run in the MATLAB core `matlab/core/*.m`**; Python only prepares GIS data, runs the solver and
writes results. ArcGIS Pro's Python cannot load the MATLAB Engine (Python 3.8-3.10 only), so a small worker runs in a
separate Python 3.10 environment and talks to the toolbox through a temp folder (JSON + raw float64 files).

> No ISO certification or conformance is claimed. Edit a `.m` file and the next run uses the new code.

## Scenarios and the ribbon add-in (new)

A **scenario** (one `.nbscenario.json` file) describes a source (location, height, Lw spectrum, directivity), terrain, a
receiver area and optionally buildings, noise barriers and a source enclosure. It is validated by 260 numbered errors,
warnings and notes (`noisebox/issues.py`), run through the same MATLAB core, and every run keeps a snapshot.
**Read `docs/NoiseBox_Manual.pdf`** (installation, every setting, a worked example with screenshots from the running software).

New in this version: allowed levels as an overall dB(A) limit **and/or** per octave band (a cell fails if any limit is exceeded); the DTM can be the map's **ground surface**; everything you create with the tools becomes a real layer in Contents (group *NoiseBox inputs*); a MATLAB engine that stays ready between runs (`docs/ENGINE_OPTIONS.md` lists the options, `fresh` = the old one-MATLAB-per-run mode is selectable in `config.json`).

| Part | Status |
|---|---|
| `noisebox/scenario*.py`, `noisebox_cli.py`, tool **5. Add-in > Run Scenario** in `NoiseBox.pyt` | built and tested |
| `matlab/core/nb_enclosure_surfaces.m` (new; `nb_enclosure.m` unchanged) and glue extensions | built and tested |
| `addin/NoiseBoxAddin` (ribbon tab, dockable pane, map tools; C#, ArcGIS Pro SDK) | **installed and used in ArcGIS Pro 3.5.3**: ribbon, pane, Preview, Run, results, input layers; map-tool sketching not clicked by a person (see the manual, section 13) |
| `dist/NoiseBox.esriAddinX` | the built add-in; install by double-click on any computer with ArcGIS Pro 3.5 |

Ribbon icons: `addin/NoiseBoxAddin/Images/<Name>16.png` and `<Name>32.png` (one pair per button, named after the id in
`Config.daml` without `NoiseBox_`). The generated placeholders come from `docs/make_icons.py`; overwrite any PNG with your
own artwork of the same name and rebuild.

Add-in troubleshooting (found while testing in ArcGIS Pro 3.5):
* Install with the `.esriAddinX` double-click or `"C:\Program Files\ArcGIS\Pro\bin\RegisterAddIn.exe" NoiseBox.esriAddinX /s`.
  Do not copy files by hand: Pro keeps its own copy in `%LOCALAPPDATA%\ESRI\ArcGISPro\AssemblyCache\{add-in id}`.
* Raise the add-in version in `Config.daml` (`AddInInfo version`) with every change, or Pro keeps the old copy.
* If a ribbon button turns grey after a click, its handler threw an exception. Every exception raised inside the add-in is
  written to `%LOCALAPPDATA%\NoiseBox\addin.log`; send that file with a bug report.
* After a Pro crash, a leftover `ArcGISPro.exe` (no window, cannot be ended without admin rights) can keep the cached
  `NoiseBoxAddin.dll` locked, so a new install does not replace it. Rename the cached file (`NoiseBoxAddin.dll` to
  `NoiseBoxAddin.dll.stale`, renaming a locked file is allowed), install again, restart Pro; a reboot also clears it.
* The ribbon icons must be written `Images\Name.png` (backslash) in `Config.daml`.

Rebuild the add-in with any .NET SDK: `.\setup\build_addin.ps1` (see the manual, section 3).
Tests: `tests/run_all.py <outdir>` runs everything (the MATLAB tests take about 30 to 40 minutes);
`tests/test_scenario.py` (validation, no MATLAB), `tests/test_cli.py`, `tests/check_addin_package.py`,
`tests/check_xaml_bindings.py`, `tests/test_scenario_engine.py` (needs MATLAB).

## The workflow (made for decisions)

| Step | Tool | What you get |
|---|---|---|
| 1 Prepare | **Create Input Layers** | empty Sources / Barriers / Receivers / Area layers with the right fields, added to the map |
| 2 Calculate | **Noise Map (LAeq raster)** | LAeq dB(A) raster, optional octave-band rasters, noise-band polygons, limit check, clickable detail cells |
| 2 Calculate | **Noise at Receivers (points)** | the same numbers as fields on receiver points (e.g. facades, homes) |
| 3 Evaluate | **Compare Noise Maps** | scenario minus baseline (e.g. with / without a barrier), share of area quieter / louder |
| 4 Utilities | **Check MATLAB Link** | Python 3.10, MATLAB Engine, `.m` hashes, solver smoke test |

Every dialog is split into numbered sections: **1 Sources, 2 Barriers & terrain, 3 Ground & atmosphere,
4 Calculation area (or Receivers), 5 Limits (optional), 6 Outputs**. All values have defaults.

### Choose or draw every input
Each input offers a drop-down of the map's layers **and** a "draw on the map" option (Pro's sketch tool in the dialog):
sources, barriers/buildings, calculation area, receivers. Drawn features get default height / Lw from the dialog
(editable). The elevation raster is chosen from a drop-down of the map's rasters; layers whose names contain
`source`, `barrier`/`building`, `area`, `receiver`, `dem`/`elev`/`srtm` are pre-selected. The **calculation area** can be
a polygon (picked or drawn; cells outside it stay empty) or a plain extent. Cell size can be left empty (automatic).

### Allowed levels (limits)
Section 5: an overall limit in dB(A) (default 55) and/or a limit per octave band (63-8000 Hz), compared with unweighted
Lp or A-weighted LpA. A cell is PASS only if every limited band **and** the overall limit are met
(`nb_compliance.m`). Outputs: **Margin** raster (dB, positive = exceedance), **PASS/FAIL** raster, the share of area above
a limit in the summary table.

### Results are grouped, one group per run
```
NoiseBox: <run>
  <run> | 1 Results          LAeq dB(A) | Noise bands dB(A) | Octave bands (unweighted Lp, 8 rasters)
  <run> | 2 Limit check      PASS/FAIL | Margin to limit
  <run> | 3 Inspect          Detail cells: click a cell to read all values
  <run> | 4 Inputs           copies of the sources / barriers / area used
```
Run names are made unique, outputs go to the geodatabase you choose, and a `<run>_Summary` table lists cells, cell
size, min / max / mean LAeq, area above limit and the physical settings.

### Click a point, read everything
The `<run>_Cells` layer holds one invisible polygon per cell (use **Identify**). Fields (per cell):
`LAeq`, `Status` (PASS/FAIL), `Margin_dBA`, `Worst_Hz`, `Worst_dB`, `Lp_63..Lp_8000` (unweighted), `LpA_63..LpA_8000`,
`DomSrc` (dominant source id), `Dist_m`, `Ground_m`, `PathType`, and the attenuations of the dominant source
`Adiv_*`, `Aatm_*`, `Agr_*`, `Abar_*` for each band (`Marg_*` per-band margins if band limits are set). Set *detail* to
"Levels only" or "None" for big grids (above 100 000 cells no detail cells are written). The receivers tool writes the same
fields onto the receiver points.

## Setup on a computer (5 steps)

Needs ArcGIS Pro 3.5+, MATLAB R2022b-R2024b, Python 3.10 (64-bit, python.org).

1. Copy this folder anywhere (all paths inside are relative to it).
2. PowerShell: `.\setup\setup_noisebox.ps1` (creates `%LOCALAPPDATA%\NoiseBox\venv310`, installs numpy and the MATLAB
   Engine; `-MatlabRoot` if MATLAB is not in `C:\Program Files\MATLAB`). Other location: env var `NOISEBOX_PY310` or
   `config.json` `{"python310": "...\\python.exe"}`.
3. Pro: Catalog > Toolboxes > Add Toolbox > `NoiseBox.pyt`.
4. Run **Check MATLAB Link** (expect 45.22 dB(A) for its smoke case and matching `.m` hashes).
5. Run **Create Input Layers**, draw or edit, then **Noise Map**. Or try the sample (below).

After editing `NoiseBox.pyt` or `noisebox/*.py`: right-click the toolbox > Refresh. Editing a `.m` needs nothing.
An elevation raster for Israel (SRTM 30 m): `propy setup\make_israel_dem.py` (needs internet; see `data/README.txt`).

### Input fields
| Layer | Field | Meaning |
|---|---|---|
| Sources (points) | `h_src` (or your height field) | height above local ground, m |
| | `Lw_63 ... Lw_8000` (prefix is a parameter) | unweighted sound power level, dB re 1 pW |
| Barriers (polygons) | `h_bar` (or your field) | height above ground, m; flat top = highest ground under the footprint + height |
| Receivers (points) | `h_rec` (optional) | receiver height above ground, m |
| DEM | any single-band elevation raster in metres | clipped, projected to the sources' CRS (bilinear); flat 0 if omitted |

Layers must use a **projected CRS in metres**; geographic CRS and feet are rejected. Barriers, DEM, area and receivers in
another CRS are projected on the fly. Other settings: ground factor G (one value for source, middle and receiver ground),
receiver height, temperature, humidity (pressure fixed at 101.325 kPa), formula mode (`iso2024` default, `draft2026`, `iso1996`).

### Sample
`sample/NoiseBox_sample.gdb` (Israeli TM Grid): `sources` (1 point), `barrier` (200 m x 0.5 m wall, 4 m high, 20 m east),
`receivers` (4 points); `sample/dem_sample.tif`. Noise Map with those layers, extent X 180030-180130 / Y 664970-665030,
cell 10 m: LAeq about 40-48 dB(A) on flat ground (41-56 with the DEM clip).

## Behaviour to know
* Sources add by energy (`nb_energy_sum`); bands combine to dB(A) with the core's A-weighting; C_met is never applied; nothing is clamped.
* Cells inside a barrier, exactly at a source, outside the DEM or outside the area polygon are NoData.
* Polygon holes of barriers are ignored; barrier tops are flat. The area polygon's holes are respected.
* Every run starts a fresh MATLAB (10-80 s), then about 7 ms per cell and source; the tool prints an estimate and stops above 2 million cell-sources.
* `Abar` is the barrier term of the core (top and lateral paths); `PathType` says whether the dominant path is free, blocked or a clear crest.

## Layout
```
NoiseBox.pyt              toolbox: parameters, sections, defaults (thin)
noisebox/                 config, exchange (worker I/O), arcgis_io (inputs, DEM, area), outputs (rasters, groups, styles), pipeline
worker/nb_worker.py       runs in Python 3.10, owns the MATLAB Engine
worker/matlab_glue/       nb_job.m: decode the job, loop sources / chunks, call the core, write results
matlab/core/              the validated solver (nb_*.m, run_*.m)
setup/, sample/, tests/   setup script, sample data, tests
```

## Tests (`propy`, outside the Pro GUI)
`tests/make_sample.py`, `tests/test_synthetic.py` (raster, bands, every detail-cell field vs direct `run_acoustic_case`),
`tests/test_other.py` (hot reload, 2 sources, drawn inputs, polygon area, DEM, receivers, compare, templates, CRS, timing),
`tests/test_pyt.py` (all tools through ArcPy's GP framework). What was **not** tested: the Pro dialogs themselves (sketching
in the dialog, section layout rendering, auto-pre-selection of map layers), clicking Identify on a detail cell, cancelling
a run, MATLAB versions other than R2023a, other computers.

## Ideas taken from
The sibling web app *noise-box* (per-band limits with PASS only if every limited band passes, point inspector, hot reload
keyed on code hashes) and common noise-mapping practice (CadnaA / SoundPLAN: map arithmetic to compare scenarios,
exceedance maps, noise-band isophones, one result set per calculation run).
