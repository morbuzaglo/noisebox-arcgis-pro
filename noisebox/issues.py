"""Catalogue of every error, warning and note NoiseBox can raise for a scenario.

Each entry: code -> (severity, pane section, message template, how to fix it).
  * severity: "error" stops the run, "warning" lets it run but the result may not mean what you expect, "info" explains.
  * section: which pane section the add-in opens when the user clicks the issue
    (scenario, source, terrain, area, structures, propagation, outputs, engine).
Messages are specific (they name the object, the band or the number) and say what to do. No arcpy, no MATLAB here.
"""
from dataclasses import dataclass, field, asdict

ERROR, WARNING, INFO = "error", "warning", "info"

# fmt: off
CATALOGUE = {
    # ---------------------------------------------------------------- scenario file
    "SCN-001": (ERROR,   "scenario", "The scenario file does not exist: {path}", "Open a scenario from the list, or create a new one."),
    "SCN-002": (ERROR,   "scenario", "The scenario file is not valid JSON ({detail}).", "Restore the file from a backup or create a new scenario; do not edit the file by hand."),
    "SCN-003": (ERROR,   "scenario", "The scenario was written by an unsupported schema version ({found}; this version reads {expected}).", "Open it with the add-in version that saved it, or re-create the scenario."),
    "SCN-004": (ERROR,   "scenario", "The scenario has no name.", "Give the scenario a name in the Scenario group; it is used for the run name and the saved file."),
    "SCN-005": (WARNING, "scenario", "The scenario file contains unknown entries ({keys}); they are kept but ignored.", "Update the add-in if the file came from a newer version."),
    "SCN-006": (ERROR,   "scenario", "The scenario has no coordinate system for the analysis (crs.wkid is empty).", "Pick a projected coordinate system in metres, e.g. Israeli TM Grid (2039) or the UTM zone of the site."),
    "SCN-007": (ERROR,   "scenario", "The analysis coordinate system {wkid} is geographic (degrees). Distances cannot be computed in degrees.", "Choose a projected, metre-based coordinate system for the analysis, e.g. {suggest}."),
    "SCN-008": (ERROR,   "scenario", "The analysis coordinate system {wkid} uses {unit} ({mpu:.6g} m per unit). NoiseBox needs metres.", "Choose a coordinate system whose linear unit is the metre."),
    "SCN-009": (ERROR,   "scenario", "The coordinate system code {wkid} is not recognised.", "Enter a valid EPSG/WKID code such as 2039 or 32636."),
    "SCN-010": (INFO,    "scenario", "Scenario saved as a snapshot: later edits do not change earlier results.", ""),

    # ---------------------------------------------------------------- source location and height
    "SRC-001": (ERROR,   "source", "No source has been placed.", "Use Source > Set Location: From Layer, Enter Coordinates or Place on Map."),
    "SRC-002": (ERROR,   "source", "The source coordinates are not valid numbers ({x}, {y}).", "Enter both coordinates as plain numbers (decimal point, no thousands separators)."),
    "SRC-003": (ERROR,   "source", "The source coordinates ({x}, {y}) cannot exist in coordinate system {wkid} ({detail}).", "Check the coordinate order ({order}) and the system selected next to the fields."),
    "SRC-004": (WARNING, "source", "The coordinates look swapped: {x}, {y} read as {order} fall outside the valid range, but swapped they are valid.", "Check that you entered {order} in that order."),
    "SRC-005": (WARNING, "source", "The source is far ({dist_km:.1f} km) from the analysis area; atmospheric absorption and ground effect will dominate.", "Check the source location and the analysis area; results this far out are of low value."),
    "SRC-006": (ERROR,   "source", "The source layer is empty or has no features that could be used: {layer}.", "Pick a layer with a point feature, or place the source on the map."),
    "SRC-007": (ERROR,   "source", "The layer {layer} contains {shape} features. A point source needs a point layer.", "Choose a point layer, or place the source on the map."),
    "SRC-008": (ERROR,   "source", "The source layer {layer} cannot be found or opened.", "Add the layer to the map again, or use Enter Coordinates."),
    "SRC-009": (WARNING, "source", "{n} points are selected in {layer}. Only one is used: {chosen}.", "Select a single point, or choose the one to use in the list."),
    "SRC-010": (ERROR,   "source", "No feature named or numbered '{key}' exists in {layer}.", "Check the name or ID, or pick the feature on the map."),
    "SRC-011": (ERROR,   "source", "The source layer {layer} has no coordinate system.", "Define the coordinate system of the layer (Define Projection) before using it."),
    "SRC-012": (WARNING, "source", "The source point has an empty geometry.", "Pick another feature or place the source on the map."),
    "SRC-013": (INFO,    "source", "Source coordinates were converted from {from_wkid} to the analysis system {to_wkid}: {x:.3f}, {y:.3f}.", ""),
    "SRC-014": (ERROR,   "source", "Source height above ground is missing.", "Enter the physical height of the source above the ground, in metres (for example 1.2)."),
    "SRC-015": (ERROR,   "source", "Source height above ground must be a number >= 0 (got {value}).", "Enter the height in metres; use 0 for a source on the ground."),
    "SRC-016": (WARNING, "source", "Source height {value} m is unusually large; check that it is a height above ground and not an elevation above sea level.", "Source height is measured from the local ground, not from sea level."),
    "SRC-017": (WARNING, "source", "Source height is 0 m: the source is exactly on the ground, where ground effect is at its extreme.", "Use a small positive height (e.g. the centre of the radiating surface) unless 0 is intended."),
    "SRC-018": (INFO,    "source", "Source elevation: ground {ground:.2f} m + height {h:.2f} m = {absolute:.2f} m above the DTM datum.", ""),
    "SRC-019": (INFO,    "source", "No DTM is selected: the source elevation will be computed when terrain is selected; until then ground is taken as 0 m.", ""),
    "SRC-020": (WARNING, "source", "The source and the layer point differ by {dist:.2f} m after unit conversion.", "Check the coordinate system of the layer."),

    # ---------------------------------------------------------------- spectrum
    "SPC-001": (ERROR,   "source", "The source spectrum is empty.", "Enter Lw in all eight octave bands (63 to 8000 Hz), paste them, or load a profile."),
    "SPC-002": (ERROR,   "source", "Sound power Lw is missing in {n} band(s): {bands} Hz. A missing value is not the same as 0 dB.", "Enter a value for every band; enter 0 only if the band really radiates 0 dB re 1 pW."),
    "SPC-003": (ERROR,   "source", "Lw at {band} Hz is not a number ({value}).", "Enter a number in dB re 1 pW."),
    "SPC-004": (WARNING, "source", "Lw at {band} Hz is negative ({value} dB). Check that these are sound power levels, not sound pressure levels or attenuations.", "Lw is normally 60 to 140 dB re 1 pW for machinery."),
    "SPC-005": (WARNING, "source", "Lw at {band} Hz is very high ({value} dB re 1 pW). Check the unit.", "Jet engines and similar are around 150 to 170 dB; machinery is usually below 130 dB."),
    "SPC-006": (WARNING, "source", "All eight Lw values are 0 dB: this is the empty default, not a measurement.", "Enter the real spectrum before running."),
    "SPC-007": (WARNING, "source", "The Lw values are the same in every band ({value} dB): the source is treated as white noise.", "Check that this is intended; machinery spectra normally slope."),
    "SPC-008": (ERROR,   "source", "The pasted values contain {n} entries; 8 are needed (one per octave band from 63 to 8000 Hz).", "Paste a row or column of exactly eight numbers, or paste two columns (frequency, level)."),
    "SPC-009": (ERROR,   "source", "The CSV file {path} could not be read ({detail}).", "Use a file with one frequency column (63 ... 8000) and one level column, with or without a header."),
    "SPC-010": (ERROR,   "source", "The CSV file contains the frequency {freq} Hz, which is not one of the eight supported octave bands.", "Use the octave bands 63, 125, 250, 500, 1000, 2000, 4000 and 8000 Hz."),
    "SPC-011": (WARNING, "source", "The CSV file has no value for {bands} Hz; those bands stay empty.", "Fill the missing bands before running."),
    "SPC-012": (ERROR,   "source", "The source profile '{name}' cannot be found.", "Choose a profile from the list or save one first."),
    "SPC-013": (ERROR,   "source", "A source profile needs a name before it can be saved.", "Type a name for the profile."),
    "SPC-014": (WARNING, "source", "A comma was found as the decimal separator in '{text}'; it was read as {value}.", "Use a decimal point to avoid ambiguity."),
    "SPC-015": (INFO,    "source", "The spectrum is the {kind} spectrum '{name}'.", ""),

    # ---------------------------------------------------------------- directivity
    "DIR-001": (INFO,    "source", "The source is omnidirectional: no directivity correction is applied (Dc = 0 dB).", ""),
    "DIR-002": (ERROR,   "source", "Directional mode needs a correction Dc in all eight bands; missing: {bands} Hz.", "Enter Dc in dB for every band (0 where there is no correction) or switch to Omnidirectional."),
    "DIR-003": (WARNING, "source", "Directivity correction Dc = {value} dB at {band} Hz is large; check the sign and the unit.", "Dc is added to Lw towards the receivers (positive = louder). Typical values are -10 to +10 dB."),
    "DIR-004": (INFO,    "source", "In this version the engine applies one constant Dc per band to every receiver. The heading ({heading} deg) is stored in the scenario but does not change the result.", "An angle-dependent directivity needs a calculation the engine does not have yet."),
    "DIR-005": (ERROR,   "source", "The source heading {value} is not a number.", "Enter the heading in degrees, 0 to 360."),
    "DIR-006": (WARNING, "source", "The source heading {value} deg is outside 0 to 360; it is read as {norm:.1f} deg.", "Headings are clockwise from grid north (map up)."),
    "DIR-007": (WARNING, "source", "An angular directivity table was given but the engine cannot use it.", "Remove the table, or use the constant per-band Dc."),

    # ---------------------------------------------------------------- terrain / DTM
    "DTM-001": (INFO,    "terrain", "No DTM selected: ground is flat at elevation 0 m. Terrain screening and ground elevation are not considered.", "Select a DTM in Terrain and Area to include terrain."),
    "DTM-002": (ERROR,   "terrain", "The DTM {path} does not exist or cannot be opened.", "Select the raster again from the list, or browse to it."),
    "DTM-003": (ERROR,   "terrain", "The DTM {path} has {bands} bands. A DTM must have one band of elevations.", "Choose a single-band elevation raster (not an image)."),
    "DTM-004": (ERROR,   "terrain", "The DTM {path} has no coordinate system.", "Define the coordinate system of the raster (Define Projection) before using it."),
    "DTM-005": (INFO,    "terrain", "The DTM is in {dtm_crs} and is projected on the fly to {to_wkid} (bilinear).", ""),
    "DTM-006": (ERROR,   "terrain", "The vertical unit of the DTM is unknown.", "Choose metres or feet for the DTM. Ground elevation in the wrong unit would be off by a factor of 3.28."),
    "DTM-007": (INFO,    "terrain", "The DTM is in {unit}; elevations are multiplied by {factor:.4f} to give metres.", ""),
    "DTM-008": (ERROR,   "terrain", "The source lies outside the DTM coverage.", "Select a DTM that covers the source, or remove the DTM to use flat ground."),
    "DTM-009": (ERROR,   "terrain", "The DTM has no data at the source location.", "Fill the NoData cell, or choose a DTM without a hole at the source."),
    "DTM-010": (WARNING, "terrain", "The DTM does not cover {pct:.0f} % of the receiver area; receivers there get no result.", "Choose a larger DTM, or reduce the analysis area. Show Coverage displays the gaps."),
    "DTM-011": (WARNING, "terrain", "{n} path(s) from the source to the receiver area cross DTM gaps; the terrain along them is unknown.", "Show Coverage marks the gaps. Receivers behind a gap get no result."),
    "DTM-012": (ERROR,   "terrain", "The DTM does not cover any part of the receiver area.", "Choose a DTM that overlaps the analysis area."),
    "DTM-013": (WARNING, "terrain", "The DTM cell size ({dtm_cell:.1f} m) is coarser than the output cell size ({cell:.1f} m); the output is finer than the terrain data.", "Use Match DTM Resolution, or accept that the terrain is smoothed."),
    "DTM-014": (WARNING, "terrain", "Elevations in the DTM range from {zmin:.0f} to {zmax:.0f} m; check the vertical unit and the nodata value.", "Typical values for most sites are -500 to 3000 m."),
    "DTM-015": (WARNING, "terrain", "The DTM is huge ({mcells:.0f} million cells in the analysis window); preparing it will be slow.", "Clip the DTM to the site first."),
    "DTM-016": (ERROR,   "terrain", "Terrain screening off is not available in this version: the engine always includes terrain diffraction when a DTM is used.", "Keep terrain screening on, or remove the DTM to run with flat ground."),
    "DTM-017": (INFO,    "terrain", "Source ground elevation {ground:.2f} m is read from the DTM cell nearest to the source; the run interpolates bilinearly.", ""),
    "DTM-018": (WARNING, "terrain", "The DTM cell size is {dtm_cell:.1f} m: structures narrower than that are not represented in the terrain, only through their own heights.", ""),

    # ---------------------------------------------------------------- analysis area / receivers
    "ARA-001": (ERROR,   "area", "No receiver area is defined.", "Terrain and Area > Set Analysis Area: use polygons, draw one, enter a radius or capture the map extent."),
    "ARA-002": (ERROR,   "area", "The receiver polygon has no geometry.", "Draw a polygon or choose features that have geometry."),
    "ARA-003": (ERROR,   "area", "The receiver polygon has fewer than 3 distinct vertices.", "A polygon needs at least three corners."),
    "ARA-004": (ERROR,   "area", "The receiver polygon crosses itself (near {x:.1f}, {y:.1f}); the inside is ambiguous.", "Edit the vertices so the outline does not cross itself."),
    "ARA-005": (ERROR,   "area", "The receiver polygon has zero area.", "The corners are on one line; move at least one vertex."),
    "ARA-006": (ERROR,   "area", "No polygon is selected in {layer}.", "Select the polygons to use, or choose the entire layer."),
    "ARA-007": (ERROR,   "area", "The layer {layer} contains {shape} features; the receiver area needs polygons.", "Choose a polygon layer or draw the area."),
    "ARA-008": (ERROR,   "area", "The radius must be a number > 0 m (got {value}).", "Enter the radius in metres, for example 500."),
    "ARA-009": (WARNING, "area", "A radius of {value} m is large; the area is {area_km2:.1f} km2.", "Calculation time grows with the area; check the unit (metres)."),
    "ARA-010": (WARNING, "area", "The radius ({value} m) is smaller than 10 m; there are very few receiver cells.", "Increase the radius or use a smaller cell size."),
    "ARA-011": (ERROR,   "area", "The captured map extent is empty or has zero width/height.", "Zoom to the area of interest and capture the extent again."),
    "ARA-012": (WARNING, "area", "The captured extent is in {wkid}, not the analysis system; it was projected and its edges may not be straight.", ""),
    "ARA-013": (INFO,    "area", "The source lies outside the receiver polygon. Results are produced only inside the polygon; terrain and structures between the source and the polygon still count.", ""),
    "ARA-014": (INFO,    "area", "The circle of radius {value} m follows the source; if the source moves, the area moves with it.", ""),
    "ARA-015": (INFO,    "area", "The captured extent stays fixed when you pan or zoom.", ""),
    "ARA-016": (ERROR,   "area", "Receiver cell size must be a number > 0 m (got {value}).", "Enter the output cell size in metres or choose Match DTM Resolution."),
    "ARA-017": (ERROR,   "area", "Match DTM Resolution needs a DTM, but none is selected.", "Select a DTM or enter a custom cell size."),
    "ARA-018": (WARNING, "area", "The cell size ({cell:.1f} m) gives only {n} cells across the area; the map will be very coarse.", "Use a smaller cell size."),
    "ARA-019": (ERROR,   "area", "The area has about {cells:,} receiver cells x {nsrc} source(s); the limit is {limit:,}.", "Use a larger cell size or a smaller area."),
    "ARA-020": (WARNING, "area", "About {cells:,} receiver cells: detail cells (click-to-read values) are skipped above {limit:,} cells.", "Use a larger cell size if you want to click on cells."),
    "ARA-021": (WARNING, "area", "Estimated run time about {minutes:.0f} min ({cells:,} cells).", "A larger cell size or a smaller area runs much faster."),
    "ARA-022": (ERROR,   "area", "Receiver height above local ground must be a number > 0 m (got {value}).", "Enter the receiver height in metres, for example 1.5 or 4."),
    "ARA-023": (WARNING, "area", "Receiver height {value} m is unusually large.", "It is measured above the terrain at each receiver cell."),
    "ARA-024": (INFO,    "area", "Receiver height is measured above the terrain at each receiver cell, not above sea level.", ""),
    "ARA-025": (ERROR,   "area", "No receiver cell centre falls inside the polygon at a cell size of {cell:.1f} m.", "Use a smaller cell size or a larger polygon."),
    "ARA-026": (WARNING, "area", "The receiver polygon extends {pct:.0f} % beyond the DTM; those receivers get no result.", ""),
    "ARA-027": (WARNING, "area", "The polygon layer has several polygons; they are combined and cells inside any of them are calculated.", ""),
    "ARA-028": (WARNING, "area", "The source is within {dist:.1f} m of a receiver cell; levels very close to a point source are not meaningful.", "ISO 9613-2 is meant for distances of at least a few metres."),
    "ARA-029": (WARNING, "area", "Receivers closer than 5 m to the source are left empty only at the source cell; nearby cells may show very high levels.", ""),
    "ARA-030": (INFO,    "area", "Receiver cell centres are used; cell size {cell:.1f} m gives {nx} x {ny} = {cells:,} cells.", ""),

    # ---------------------------------------------------------------- structures (general)
    "STR-001": (ERROR,   "structures", "Two structures share the name '{name}'.", "Give each structure a unique name."),
    "STR-002": (ERROR,   "structures", "The structure has no name.", "Give the structure a name so you can find it in the list."),
    "STR-003": (ERROR,   "structures", "'{name}' has an unknown type '{type}'.", "Structures are Building, Barrier or Enclosure."),
    "STR-004": (INFO,    "structures", "'{name}' is hidden on the map but still takes part in the calculation.", "Participation is the Include in Analysis checkbox; visibility only controls drawing."),
    "STR-005": (INFO,    "structures", "'{name}' is shown on the map but excluded from the calculation.", "Tick Include in Analysis to use it."),
    "STR-006": (INFO,    "structures", "{n_inc} of {n} structure(s) take part in the run.", ""),
    "STR-007": (WARNING, "structures", "'{name}' refers to a GIS feature that is no longer in {layer}; the geometry saved in the scenario is used.", "Re-link the object to the layer, or keep the saved geometry."),
    "STR-008": (ERROR,   "structures", "'{name}' has no geometry.", "Draw it on the map, pick a feature or enter its dimensions."),
    "STR-009": (WARNING, "structures", "'{name}' lies outside the DTM and the receiver area; it cannot affect the result.", "Move it or exclude it."),
    "STR-010": (WARNING, "structures", "'{name}' does not lie between the source and any receiver; it has no effect on the result.", ""),
    "STR-011": (INFO,    "structures", "The GIS feature behind '{name}' is not modified; edits are stored in the scenario.", ""),
    "STR-012": (WARNING, "structures", "Reflections from structures are not available in this version. Only screening (diffraction){extra} is calculated for '{name}'.", "ISO 9613-2 cl. 7.5 image sources are not implemented."),
    "STR-013": (ERROR,   "structures", "'{name}' has a non-finite coordinate ({x}, {y}).", "Re-draw the object."),
    "STR-014": (WARNING, "structures", "'{name}' is more than {limit} vertices long; only {limit} are kept for the run.", ""),
    "STR-015": (WARNING, "structures", "'{name}' is inactive in this run because Include in Analysis is off.", ""),

    # ---------------------------------------------------------------- buildings
    "BLD-001": (ERROR,   "structures", "Building '{name}' has no footprint.", "Draw a footprint or choose a polygon."),
    "BLD-002": (ERROR,   "structures", "Building '{name}' has fewer than 3 distinct vertices.", "A footprint needs at least three corners."),
    "BLD-003": (ERROR,   "structures", "Building '{name}': the footprint crosses itself near {x:.1f}, {y:.1f}.", "Edit the vertices so the outline does not cross itself."),
    "BLD-004": (ERROR,   "structures", "Building '{name}': height above ground is missing.", "Enter a height in metres, or choose the field that holds it."),
    "BLD-005": (ERROR,   "structures", "Building '{name}': height must be a number > 0 m (got {value}).", "Enter the height above ground in metres."),
    "BLD-006": (WARNING, "structures", "Building '{name}': height {value} m is unusual; check the unit.", "Buildings are usually 3 to 150 m."),
    "BLD-007": (ERROR,   "structures", "The height field '{field}' in {layer} does not exist.", "Choose one of: {choices}."),
    "BLD-008": (ERROR,   "structures", "The height field '{field}' is not numeric (type {ftype}).", "Choose a numeric field (Double, Single, Integer)."),
    "BLD-009": (WARNING, "structures", "{n} feature(s) in {layer} have no value in '{field}' (OIDs {oids}); they use the default height {default} m.", "Fill the field, or accept the default."),
    "BLD-010": (WARNING, "structures", "The height field '{field}' has no unit; values are taken as metres (largest value {vmax}).", "If they are in feet, convert them or tick the feet option."),
    "BLD-011": (INFO,    "structures", "Imported {n} buildings; heights {hmin:.1f} to {hmax:.1f} m (field '{field}', metres).", ""),
    "BLD-012": (ERROR,   "structures", "The source lies inside building '{name}'.", "Move the source, or model the building as an Enclosure of the source."),
    "BLD-013": (INFO,    "structures", "Receiver cells inside building footprints are left empty (NoData). {n} cell(s) are affected in this run.", ""),
    "BLD-014": (INFO,    "structures", "Receivers inside buildings: {policy}.", ""),
    "BLD-015": (WARNING, "structures", "{n} building footprints overlap; each is a separate screen. Overlapping footprints are not merged.", ""),
    "BLD-016": (WARNING, "structures", "Building '{name}' has an interior ring (courtyard); holes are ignored and the footprint is treated as solid.", ""),
    "BLD-017": (INFO,    "structures", "Building '{name}': the effect in this version is screening only (top and side diffraction). No reflections or facade effects.", ""),
    "BLD-018": (WARNING, "structures", "Building '{name}' is smaller than {minw:.1f} m across; for low frequencies it does not screen (ISO 9613-2:2024 7.4.1).", ""),
    "BLD-019": (ERROR,   "structures", "Importing {n} buildings would exceed the limit of {limit} structures in one scenario.", "Select fewer buildings or clip them to the area."),
    "BLD-020": (WARNING, "structures", "{n} buildings lie wholly outside the analysis area plus the source; they were skipped.", ""),

    # ---------------------------------------------------------------- noise barriers
    "BAR-001": (ERROR,   "structures", "Barrier '{name}' has no path.", "Draw it on the map, pick a polyline, or enter start point, length, azimuth and height."),
    "BAR-002": (ERROR,   "structures", "Barrier '{name}' needs at least two distinct vertices.", "Add a second point."),
    "BAR-003": (ERROR,   "structures", "Barrier '{name}' has zero length.", "Enter a length > 0 m or move the end point."),
    "BAR-004": (ERROR,   "structures", "Barrier '{name}': height is missing.", "Enter the height above ground or the absolute top elevation, in metres."),
    "BAR-005": (ERROR,   "structures", "Barrier '{name}': height must be a number > 0 m (got {value}).", "Enter the height in metres."),
    "BAR-006": (WARNING, "structures", "Barrier '{name}': height {value} m is unusual for a noise barrier (usually 1 to 12 m).", ""),
    "BAR-007": (ERROR,   "structures", "Barrier '{name}': the vertical definition is '{mode}'; use 'relative' (above local terrain) or 'absolute' (top elevation).", "Choose one of the two vertical definitions."),
    "BAR-008": (ERROR,   "structures", "Barrier '{name}': the absolute top elevation {top:.2f} m is below the ground ({ground:.2f} m) at {where}.", "Raise the top or use a height above local terrain."),
    "BAR-009": (WARNING, "structures", "Barrier '{name}': at some points the absolute top is only {clear:.2f} m above ground.", "Check the profile preview; a barrier that low barely screens."),
    "BAR-010": (WARNING, "structures", "Barrier '{name}': 'height above local terrain' becomes a flat top at {top:.2f} m (highest ground under the barrier + {h:.2f} m); the engine uses a flat top per barrier segment.", "Split the barrier into shorter segments on sloping ground if the top should follow the terrain."),
    "BAR-011": (ERROR,   "structures", "Barrier '{name}': start point, length and azimuth are all needed (missing: {missing}).", "Fill the missing fields."),
    "BAR-012": (ERROR,   "structures", "Barrier '{name}': azimuth {value} is not a number.", "Enter the azimuth in degrees clockwise from grid north (map up)."),
    "BAR-013": (INFO,    "structures", "Barrier '{name}': azimuth {az:.1f} deg clockwise from north; end point {x:.2f}, {y:.2f}.", ""),
    "BAR-014": (ERROR,   "structures", "Barrier '{name}': the layer {layer} contains {shape} features; a barrier needs polylines.", "Choose a polyline layer or draw the barrier."),
    "BAR-015": (WARNING, "structures", "Barrier '{name}' passes through or within 1 m of the source.", "Check the geometry; a barrier on top of the source gives unreliable results."),
    "BAR-016": (WARNING, "structures", "Barrier '{name}' passes through a building footprint.", "Barrier and building are calculated separately; check that this is intended."),
    "BAR-017": (WARNING, "structures", "Barrier '{name}' has {n} segments; each is a separate diffracting wall. Gaps between segments are open.", "Close the gaps in the path if it is meant to be continuous."),
    "BAR-018": (WARNING, "structures", "Barrier '{name}' is only {length:.1f} m long; for low frequencies it does not screen (ISO 9613-2:2024 7.4.1).", ""),
    "BAR-019": (INFO,    "structures", "Barrier '{name}' is calculated as: {kind}.", ""),
    "BAR-020": (ERROR,   "structures", "Barrier '{name}' is not covered by the DTM at {where}; its ground level is unknown.", "Choose a DTM that covers the barrier, or remove the DTM."),
    "BAR-021": (WARNING, "structures", "Barrier '{name}' lies outside the DTM along {pct:.0f} % of its length.", ""),
    "BAR-022": (ERROR,   "structures", "Barrier '{name}': a surface mass or transmission loss is required for transmission, but none is given.", "Enter surface density or octave-band TL, or turn transmission off (diffraction only)."),
    "BAR-023": (WARNING, "structures", "Barrier '{name}': surface mass {m:.1f} kg/m2 is below 10 kg/m2; ISO 9613-2:2024 7.4.1 requires at least 10 kg/m2 for a screening object.", "Treat the result as an opaque-screen estimate or use a heavier material."),
    "BAR-024": (INFO,    "structures", "Barrier '{name}' is calculated by diffraction only; no material properties are needed.", ""),
    "BAR-025": (INFO,    "structures", "Barrier '{name}' is calculated by diffraction plus transmission through the barrier (energy sum; an engineering approximation, not part of ISO 9613-2).", ""),
    "BAR-026": (ERROR,   "structures", "Barrier '{name}': the barrier is hanging with a gap of {gap} m, which must be >= 0 and below the top.", "Set the bottom gap to 0 for a barrier that reaches the ground."),
    "BAR-027": (WARNING, "structures", "Barrier '{name}' has been moved or edited; its GIS source feature is unchanged.", ""),
    "BAR-028": (ERROR,   "structures", "Barrier '{name}': length {value} is not a number > 0 m.", "Enter the length in metres."),
    "BAR-029": (WARNING, "structures", "Barrier '{name}' is closer than 1 m to the receiver area; cells next to it are strongly affected.", ""),
    "BAR-030": (WARNING, "structures", "Barrier '{name}' does not block the line of sight to any receiver.", "It has no effect on this scenario; check its position and height."),

    # ---------------------------------------------------------------- enclosures
    "ENC-001": (ERROR,   "structures", "Enclosure '{name}' is not linked to a source.", "Select the source it encloses."),
    "ENC-002": (ERROR,   "structures", "Enclosure '{name}' has no footprint.", "Use the quick rectangle (length, width, height, orientation) or draw a polygon."),
    "ENC-003": (ERROR,   "structures", "Enclosure '{name}': length, width and height must all be numbers > 0 m (length {l}, width {w}, height {h}).", "Enter the three dimensions in metres."),
    "ENC-004": (ERROR,   "structures", "Enclosure '{name}': the source is outside the enclosure footprint ({dx:.2f} m from the nearest wall).", "Move the enclosure so the source is inside it, or move the source."),
    "ENC-005": (ERROR,   "structures", "Enclosure '{name}': the source height {hs:.2f} m is above the roof ({h:.2f} m).", "Raise the roof or lower the source."),
    "ENC-006": (WARNING, "structures", "Enclosure '{name}': the source is only {dist:.2f} m from a wall; the diffuse-field model needs the source to be well inside.", "Use a larger enclosure or take the result as indicative."),
    "ENC-007": (ERROR,   "structures", "Enclosure '{name}': the roof has no material.", "Assign a material to the roof (it can be the same as the walls)."),
    "ENC-008": (ERROR,   "structures", "Enclosure '{name}': wall {wall} has no material.", "Assign a material, or use one material for all walls."),
    "ENC-009": (ERROR,   "structures", "Enclosure '{name}', {face}: TL is missing at {bands} Hz.", "Enter TL for every octave band, or switch the face to Mass Law."),
    "ENC-010": (ERROR,   "structures", "Enclosure '{name}', {face}: absorption coefficient alpha is missing at {bands} Hz. It is needed for the interior sound level.", "Enter alpha (0 to 1) for every band; the enclosure model cannot run without interior absorption."),
    "ENC-011": (ERROR,   "structures", "Enclosure '{name}', {face}: alpha at {band} Hz is {value}; it must be between 0 and 1. It is a coefficient, not a dB value.", "Enter a value such as 0.1 (reflective) to 0.9 (highly absorbing)."),
    "ENC-012": (ERROR,   "structures", "Enclosure '{name}', {face}: TL at {band} Hz is {value} dB; it cannot be negative.", "Enter the transmission loss as a positive dB value."),
    "ENC-013": (WARNING, "structures", "Enclosure '{name}', {face}: TL at {band} Hz is {value} dB, which is higher than a single panel normally achieves.", "Check the unit; typical single panels give 10 to 60 dB."),
    "ENC-014": (ERROR,   "structures", "Enclosure '{name}', {face}: Mass Law needs a surface density (kg/m2) or a thickness and a volumetric density (kg/m3).", "Enter one of the two."),
    "ENC-015": (ERROR,   "structures", "Enclosure '{name}', {face}: the surface density must be a number > 0 kg/m2 (got {value}).", "Enter the mass per square metre of the panel."),
    "ENC-016": (ERROR,   "structures", "Enclosure '{name}', {face}: thickness and volumetric density must both be > 0 (thickness {t}, density {rho}).", "Enter both, in metres and kg/m3."),
    "ENC-017": (ERROR,   "structures", "Enclosure '{name}', {face}: thickness x density is only the surface mass of a homogeneous solid layer.", "For fabrics, composites or cavity panels enter the surface density directly."),
    "ENC-018": (WARNING, "structures", "Enclosure '{name}', {face}: the mass-law TL is an estimate, not a measurement; it can overestimate near coincidence and below the panel resonance.", "Use manufacturer octave-band TL where you have it."),
    "ENC-019": (WARNING, "structures", "Enclosure '{name}', {face}: surface mass {m:.1f} kg/m2 is very light for an acoustic enclosure panel.", ""),
    "ENC-020": (ERROR,   "structures", "Enclosure '{name}': the opening area {open} m2 is larger than the total surface {total:.1f} m2.", "Reduce the opening area."),
    "ENC-021": (WARNING, "structures", "Enclosure '{name}': openings of {open:.2f} m2 limit the achievable reduction to {limit:.1f} dB.", "Close or attenuate the openings (silencers) to get more reduction."),
    "ENC-022": (WARNING, "structures", "Enclosure '{name}': in {bands} Hz the radiated power would exceed the source power; the diffuse-field model does not apply there.", "Increase the interior absorption (alpha) or the area of absorptive surfaces."),
    "ENC-023": (INFO,    "structures", "Enclosure '{name}' is applied once, as a reduction of the radiated sound power (diffuse-field model, EN ISO 15667 style). It is not also treated as a barrier.", ""),
    "ENC-024": (WARNING, "structures", "Enclosure '{name}' is excluded from the analysis: the source radiates its bare power.", "Tick Include in Analysis to apply it."),
    "ENC-025": (INFO,    "structures", "Enclosure '{name}': {s_total:.1f} m2 of radiating surface, {a_in:.1f} m2 of interior absorption (broadband mean).", ""),
    "ENC-026": (ERROR,   "structures", "Enclosure '{name}': the orientation {value} is not a number.", "Enter the orientation in degrees clockwise from grid north."),
    "ENC-027": (ERROR,   "structures", "Source '{name}' already has an enclosure; only one enclosure per source is supported.", "Remove or merge the enclosures."),
    "ENC-028": (WARNING, "structures", "Enclosure '{name}': the data of face {face} is estimated (mass law); the rest is measured.", "The result mixes measured and estimated values."),
    "ENC-029": (WARNING, "structures", "Enclosure '{name}' extends outside the analysis area; receiver cells inside it are left empty.", ""),
    "ENC-030": (INFO,    "structures", "The floor is treated as ground: it does not radiate and does not absorb in this model.", ""),
    "ENC-031": (ERROR,   "structures", "Enclosure '{name}': placement offset ({dx}, {dy}) is not a pair of numbers.", "Enter the offset of the enclosure centre relative to the source in metres."),
    "ENC-032": (WARNING, "structures", "Enclosure '{name}' contains no walls with area; check the dimensions.", ""),
    "ENC-033": (ERROR,   "structures", "Enclosure '{name}': the footprint polygon crosses itself near {x:.1f}, {y:.1f}.", "Edit the vertices."),
    "ENC-034": (ERROR,   "structures", "Enclosure '{name}': the roof height above ground must be > 0 (got {h}).", "Enter the enclosure height in metres."),
    "ENC-035": (INFO,    "structures", "TL and alpha: the panel TL (dB) is the loss through a panel; alpha (0 to 1) is the absorption of its interior face. They are used separately.", ""),

    # ---------------------------------------------------------------- propagation
    "PRP-001": (ERROR,   "propagation", "The ground factor G must be between 0 (hard) and 1 (porous); got {value}.", "Use 0 for water, concrete or asphalt; 1 for grass, soil or fields."),
    "PRP-002": (ERROR,   "propagation", "The ground factor {which} is missing.", "Enter a value from 0 to 1 or switch back to a single uniform G."),
    "PRP-003": (INFO,    "propagation", "Uniform ground G = {value:.2f} is used for the source, middle and receiver regions.", ""),
    "PRP-004": (WARNING, "propagation", "Ground: separate source/middle/receiver factors are used (Gs {gs}, Gm {gm}, Gr {gr}).", "Check that the three regions match the site."),
    "PRP-005": (ERROR,   "propagation", "Temperature {value} deg C is outside the supported range of -40 to 50 deg C.", "Enter the air temperature in degrees Celsius."),
    "PRP-006": (ERROR,   "propagation", "Relative humidity must be above 0 and at most 100 %; got {value}.", "Enter a percentage, for example 70."),
    "PRP-007": (ERROR,   "propagation", "Atmospheric pressure must be a number > 0 kPa (got {value}).", "Standard pressure is 101.325 kPa."),
    "PRP-008": (WARNING, "propagation", "Atmospheric pressure {value} kPa is far from normal (80 to 110 kPa); check the unit (kPa, not hPa or Pa).", ""),
    "PRP-009": (WARNING, "propagation", "The air is very dry ({value} % RH); absorption at high frequencies is at its maximum.", ""),
    "PRP-010": (ERROR,   "propagation", "The prediction mode '{value}' is not one of iso2024, draft2026, iso1996.", "Choose a mode from the list."),
    "PRP-011": (INFO,    "propagation", "Prediction mode {mode}: {desc}.", ""),
    "PRP-012": (WARNING, "propagation", "The mode draft2026 follows a draft amendment and is not a published edition.", "Use iso2024 for results that must refer to a published edition."),
    "PRP-013": (WARNING, "propagation", "The mode iso1996 is the superseded 1996 edition; atmospheric pressure is not used in it.", "Use iso2024 unless you must reproduce an older calculation."),
    "PRP-014": (INFO,    "propagation", "Meteorology: favourable propagation (downwind or temperature inversion); no meteorological correction is applied.", ""),
    "PRP-015": (ERROR,   "propagation", "Long-term average meteorology needs the correction constant C0 (dB); it is empty.", "Enter C0 (0 to about 5 dB) from local wind and temperature-gradient statistics, or choose Favourable."),
    "PRP-016": (ERROR,   "propagation", "C0 must be a number >= 0 dB (got {value}).", "Enter C0 in dB, typically 0 to 5."),
    "PRP-017": (WARNING, "propagation", "C0 = {value} dB is above the practical range of 0 to about 5 dB given by the standard.", ""),
    "PRP-018": (INFO,    "propagation", "Long-term level: C_met is subtracted from the A-weighted levels with C0 = {value} dB (zero for short distances). Unweighted band levels are not corrected.", ""),
    "PRP-019": (WARNING, "propagation", "C0 is set but the method is 'favourable'; C0 is ignored.", "Choose Long-term average to apply C0."),
    "PRP-020": (INFO,    "propagation", "Active effects: {effects}.", ""),
    "PRP-021": (INFO,    "propagation", "Where terrain and structures obstruct the same path the engine takes the highest obstruction once; attenuations are not added twice.", ""),
    "PRP-022": (WARNING, "propagation", "A mapped ground classification was given but the engine cannot use it.", "Use uniform G or separate source/middle/receiver factors."),

    # ---------------------------------------------------------------- outputs
    "OUT-001": (ERROR,   "outputs", "No output geodatabase has been chosen.", "Choose a file geodatabase (.gdb) in Outputs."),
    "OUT-002": (ERROR,   "outputs", "The output geodatabase does not exist: {path}", "Choose an existing .gdb or create one in Catalog."),
    "OUT-003": (ERROR,   "outputs", "{path} is not a file geodatabase (it must end in .gdb).", "Choose a .gdb; rasters cannot be saved into a plain folder here."),
    "OUT-004": (ERROR,   "outputs", "The output geodatabase {path} is not writable ({detail}).", "Close other programs using it, check the folder permissions, or choose another geodatabase."),
    "OUT-005": (ERROR,   "outputs", "The run name is empty.", "Type a run name; it prefixes every output dataset."),
    "OUT-006": (WARNING, "outputs", "The run name '{name}' contains characters that are not allowed in dataset names; it becomes '{valid}'.", ""),
    "OUT-007": (INFO,    "outputs", "A run named '{name}' already exists; the new outputs are named '{unique}'.", "Earlier results are never overwritten."),
    "OUT-008": (ERROR,   "outputs", "No output is selected.", "Tick at least one of: overall A-weighted LAeq, unweighted sum, octave-band rasters."),
    "OUT-009": (ERROR,   "outputs", "'{value}' is not an octave band (63, 125, 250, 500, 1000, 2000, 4000, 8000).", "Choose bands from the list."),
    "OUT-010": (INFO,    "outputs", "Only the selected bands are saved as rasters; all eight bands are always used for the overall levels.", ""),
    "OUT-011": (INFO,    "outputs", "Datasets that will be created: {names}.", ""),
    "OUT-012": (ERROR,   "outputs", "The shared colour scale is invalid (minimum {vmin} is not below maximum {vmax}).", "Enter a minimum smaller than the maximum, in dB."),
    "OUT-013": (WARNING, "outputs", "The computed levels ({lmin:.0f} to {lmax:.0f} dB) fall partly outside the shared colour scale ({vmin:.0f} to {vmax:.0f} dB).", "Cells outside the scale take the end colours."),
    "OUT-014": (ERROR,   "outputs", "The overall limit must be a number (got {value}).", "Enter the allowed level in dB(A)."),
    "OUT-015": (WARNING, "outputs", "No map is open; results are saved in the geodatabase and not added to Contents.", "Open a map and run again to see them."),
    "OUT-016": (INFO,    "outputs", "Receivers inside building footprints: left empty (NoData).", ""),
    "OUT-017": (ERROR,   "outputs", "The scenario snapshot could not be saved ({detail}).", "Check that the output folder is writable."),
    "OUT-018": (WARNING, "outputs", "The output geodatabase is inside a synchronised folder ({detail}); sync can lock rasters while they are written.", "Use a local geodatabase if saving fails."),
    "OUT-019": (WARNING, "outputs", "The output name '{name}' is longer than 50 characters; it was shortened.", ""),

    # ---------------------------------------------------------------- engine / run
    "ENG-001": (ERROR,   "engine", "The Python 3.10 environment for MATLAB was not found ({path}).", "Run setup\\setup_noisebox.ps1, or set NOISEBOX_PY310. See Check MATLAB Link."),
    "ENG-002": (ERROR,   "engine", "The MATLAB Engine for Python is not installed in {path}.", "Run setup\\setup_noisebox.ps1 again with -MatlabRoot pointing to your MATLAB."),
    "ENG-003": (ERROR,   "engine", "The MATLAB core folder is missing: {path}", "Restore the matlab\\core folder, or set NOISEBOX_CORE_DIR."),
    "ENG-004": (WARNING, "engine", "The .m files MATLAB loaded differ from those on disk; results may use an older version of the core.", "Close other MATLAB sessions and run again."),
    "ENG-005": (ERROR,   "engine", "MATLAB stopped before it finished ({detail}).", "Check MATLAB has a licence and is not open elsewhere; run Check MATLAB Link."),
    "ENG-006": (ERROR,   "engine", "The run was cancelled.", "Run again when ready; nothing was written."),
    "ENG-007": (ERROR,   "engine", "No receiver cell has a valid result. Typical reasons: the polygon lies outside the DTM, all cells are inside buildings, or the source coincides with a cell.", "Check coverage in Preview."),
    "ENG-008": (WARNING, "engine", "{pct:.0f} % of the receiver cells have no result (outside the DTM, inside a structure, or at the source).", "Show Coverage and the structure footprints explain the gaps."),
    "ENG-009": (ERROR,   "engine", "The core rejected the input: {detail}", "Correct the value named in the message."),
    "ENG-010": (WARNING, "engine", "MATLAB takes 10 to 80 s to start; the run begins after that.", ""),
    "ENG-011": (INFO,    "engine", "Calculated with MATLAB {matlab}, core files {nfiles}, mode {mode}.", ""),
    "ENG-012": (ERROR,   "engine", "The glue script worker\\matlab_glue\\nb_job.m is missing ({path}).", "Restore the worker folder."),
    "ENG-013": (ERROR,   "engine", "The worker could not write to the temporary folder ({detail}).", "Free disk space or set TEMP to a writable folder."),
    "ENG-014": (WARNING, "engine", "The enclosure model reports that it does not apply in {bands} Hz for source '{name}'.", "Increase the interior absorption."),
    "ENG-015": (ERROR,   "engine", "ArcGIS Pro's Python (arcpy) is not available; the analysis cannot read GIS data.", "Run the add-in from ArcGIS Pro, or use propy."),
}
# fmt: on


class _Default(dict):
    def __missing__(self, key):
        return "?"


@dataclass
class Issue:
    code: str
    severity: str
    section: str
    message: str
    fix: str = ""
    object_id: str = ""          # structure id, when the issue belongs to one object
    field: str = ""              # input to focus in the pane (e.g. "source.height")

    def as_dict(self):
        return asdict(self)

    def __str__(self):
        return "[%s] %s: %s%s" % (self.code, self.severity.upper(), self.message, ("  -> " + self.fix) if self.fix else "")


def make(code, object_id="", field="", **kw):
    """Build an Issue from the catalogue. Unknown placeholders print as '?'; unknown codes raise KeyError."""
    sev, section, msg, fix = CATALOGUE[code]
    try:
        m = msg.format_map(_Default(kw))
        f = fix.format_map(_Default(kw))
    except (ValueError, IndexError):          # a number that cannot take its format spec
        m, f = msg, fix
        for k, v in kw.items():
            m = m.replace("{%s}" % k, str(v))
            f = f.replace("{%s}" % k, str(v))
    return Issue(code, sev, section, m, f, object_id, field)


def has_errors(issues):
    return any(i.severity == ERROR for i in issues)


def counts(issues):
    return {s: sum(1 for i in issues if i.severity == s) for s in (ERROR, WARNING, INFO)}


def sort_issues(issues):
    order = {ERROR: 0, WARNING: 1, INFO: 2}
    return sorted(issues, key=lambda i: (order[i.severity], i.section, i.code))
