using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using ArcGIS.Desktop.Core;
using ArcGIS.Desktop.Framework;
using ArcGIS.Desktop.Framework.Contracts;
using ArcGIS.Desktop.Framework.Threading.Tasks;
using ArcGIS.Desktop.Mapping;
using NoiseBoxAddin.Core;

namespace NoiseBoxAddin.UI
{
    internal partial class NoiseBoxPaneViewModel
    {
        // ---------------------------------------------------------------- commands
        public ICommand PreviewCommand { get; private set; }
        public ICommand RunCommand { get; private set; }
        public ICommand FindSourceCommand { get; private set; }
        public ICommand UseCandidateCommand { get; private set; }
        public ICommand ApplyCoordinatesCommand { get; private set; }
        public ICommand PasteSpectrumCommand { get; private set; }
        public ICommand ImportCsvCommand { get; private set; }
        public ICommand SaveProfileCommand { get; private set; }
        public ICommand LoadProfileCommand { get; private set; }
        public ICommand UseRasterCommand { get; private set; }
        public ICommand UseGroundCommand { get; private set; }
        public ICommand EngineStatusCommand { get; private set; }
        public ICommand EngineStopCommand { get; private set; }
        public ICommand ClearLimitsCommand { get; private set; }
        public ICommand BrowseDtmCommand { get; private set; }
        public ICommand ShowCoverageCommand { get; private set; }
        public ICommand UsePolygonsCommand { get; private set; }
        public ICommand CaptureExtentCommand { get; private set; }
        public ICommand UseRadiusCommand { get; private set; }
        public ICommand BrowseGdbCommand { get; private set; }
        public ICommand ShowAtmosphereCommand { get; private set; }
        public ICommand EstimateMaterialCommand { get; private set; }
        public ICommand ZoomCommand { get; private set; }
        public ICommand DuplicateStructureCommand { get; private set; }
        public ICommand RemoveStructureCommand { get; private set; }
        public ICommand EditStructureCommand { get; private set; }
        public ICommand GoToIssueCommand { get; private set; }
        public ICommand ProfilePreviewCommand { get; private set; }
        public ICommand RefreshListsCommand { get; private set; }

        /// <summary>A command whose exceptions show in the status line and in addin.log instead of silently disabling the button.</summary>
        private RelayCommand SafeCmd(Func<Task> body, Func<bool> can = null) => new RelayCommand(async () =>
        {
            try { await body(); }
            catch (Exception e) { Status = "Error: " + e.Message; Log.Write("COMMAND " + e); }
        }, can ?? (() => true));

        private void BuildCommands()
        {
            PreviewCommand = SafeCmd(async () => await RefreshIssuesAsync(true), () => true);
            RunCommand = SafeCmd(async () => await RunAsync(), () => true);
            FindSourceCommand = SafeCmd(async () => await FindSourceAsync(), () => true);
            UseCandidateCommand = new RelayCommand(() => { if (SelectedCandidate != null) ApplyCandidate(SelectedCandidate); }, () => true);
            ApplyCoordinatesCommand = SafeCmd(async () => await ApplyCoordinatesAsync(), () => true);
            PasteSpectrumCommand = SafeCmd(async () => await PasteSpectrumAsync(Clipboard.GetText()), () => true);
            ImportCsvCommand = SafeCmd(async () => await ImportCsvAsync(), () => true);
            SaveProfileCommand = SafeCmd(async () => await SaveProfileAsync(), () => true);
            LoadProfileCommand = SafeCmd(async () => await LoadProfileAsync(), () => true);
            UseRasterCommand = SafeCmd(async () => await UseRasterAsync(), () => true);
            UseGroundCommand = SafeCmd(async () => await UseGroundSurfaceAsync(), () => true);
            EngineStatusCommand = SafeCmd(async () => await ShowEngineAsync(false), () => true);
            EngineStopCommand = SafeCmd(async () => await ShowEngineAsync(true), () => true);
            ClearLimitsCommand = new RelayCommand(() => ClearLimits(), () => true);
            BrowseDtmCommand = SafeCmd(async () => await BrowseDtmAsync(), () => true);
            ShowCoverageCommand = SafeCmd(async () => { await RefreshIssuesAsync(true); Status = CoverageText; }, () => true);
            UsePolygonsCommand = SafeCmd(async () => await UsePolygonsAsync(), () => true);
            CaptureExtentCommand = SafeCmd(async () => await CaptureExtentAsync(), () => true);
            UseRadiusCommand = new RelayCommand(() => UseRadius(), () => true);
            BrowseGdbCommand = new RelayCommand(() => BrowseGdb(), () => true);
            ShowAtmosphereCommand = SafeCmd(async () => await ShowAtmosphereAsync(), () => true);
            EstimateMaterialCommand = SafeCmd(async () => await EstimateMaterialAsync(), () => true);
            ZoomCommand = SafeCmd(async () => await ZoomToSelectedAsync(), () => SelectedId != null);
            DuplicateStructureCommand = new RelayCommand(() => { if (SelectedId != null) { var d = Doc.DuplicateStructure(SelectedId); RebuildStructures((string)d["id"]); } }, () => SelectedId != null);
            RemoveStructureCommand = new RelayCommand(() => { if (SelectedId != null) { Doc.RemoveStructure(SelectedId); RebuildStructures(); } }, () => SelectedId != null);
            EditStructureCommand = new RelayCommand(() => { OpenSection("structures"); FocusRequested?.Invoke("sname"); }, () => SelectedId != null);
            GoToIssueCommand = new RelayCommand(() => { if (SelectedIssue != null) GoTo(SelectedIssue); }, () => true);
            ProfilePreviewCommand = SafeCmd(async () => await BarrierProfileAsync(), () => SelectedId != null);
            RefreshListsCommand = SafeCmd(async () => await RefreshListsAsync(), () => true);
        }

        // ---------------------------------------------------------------- source: from layer
        private LayerItem _pointLayer;
        public LayerItem SelectedPointLayer { get => _pointLayer; set { _pointLayer = value; NotifyPropertyChanged(); } }
        public bool UseSelectedFeature { get; set; } = true;
        public string KeyText { get; set; }
        public ObservableCollection<PointCandidate> Candidates { get; } = new ObservableCollection<PointCandidate>();
        public PointCandidate SelectedCandidate { get; set; }

        /// <summary>From Layer: the feature already selected on the layer, or one found by name / ID. Several matches: the user chooses.</summary>
        public async Task FindSourceAsync()
        {
            Candidates.Clear();
            if (SelectedPointLayer?.Layer is not FeatureLayer fl) { Status = "Choose a point layer first (SRC-008)."; return; }
            var list = UseSelectedFeature ? await ProApi.SelectedPointsAsync(fl) : await ProApi.FindPointsAsync(fl, KeyText ?? "");
            if (list.Count == 0)
            {
                Status = UseSelectedFeature ? $"No point is selected in {fl.Name}. Select one on the map, or search by name or ID (SRC-006)."
                                            : $"No feature named or numbered '{KeyText}' in {fl.Name} (SRC-010).";
                return;
            }
            if (list.Count == 1) { ApplyCandidate(list[0], fl); return; }
            foreach (var c in list) Candidates.Add(c);
            Status = $"{list.Count} points match in {fl.Name}: choose the one to use (SRC-009).";
        }

        private void ApplyCandidate(PointCandidate c, FeatureLayer fl = null)
        {
            fl ??= SelectedPointLayer?.Layer as FeatureLayer;
            Doc.SetSourceLocation("layer", c.X, c.Y, c.Wkid, fl == null ? null : ProApi.LayerRef(fl, c.Oid));
            Candidates.Clear();
            ShowSourceCoordinates();
            Status = $"Source set from {fl?.Name}: {c.Label}.";
        }

        // ---------------------------------------------------------------- source: enter coordinates
        private string _cx = "", _cy = "", _cw = "2039", _lx = "Easting", _ly = "Northing", _hint = "Order: Easting, Northing; metres";
        public string CoordX { get => _cx; set { _cx = value; NotifyPropertyChanged(); } }
        public string CoordY { get => _cy; set { _cy = value; NotifyPropertyChanged(); } }
        public string CoordLabelX { get => _lx; private set { _lx = value; NotifyPropertyChanged(); } }
        public string CoordLabelY { get => _ly; private set { _ly = value; NotifyPropertyChanged(); } }
        public string CoordHint { get => _hint; private set { _hint = value; NotifyPropertyChanged(); } }
        public string[] CommonSystems { get; } = { "2039", "4326", "32636", "32633", "3857" };

        public string CoordWkid
        {
            get => _cw;
            set { _cw = value; NotifyPropertyChanged(); _ = UpdateCoordinateLabelsAsync(); }
        }

        private bool _showCoords = true;
        public bool ShowCoordinateFields { get => _showCoords; set { _showCoords = value; NotifyPropertyChanged(); } }

        /// <summary>Labels follow the system: Easting/Northing for projected, Longitude/Latitude for geographic.</summary>
        public async Task UpdateCoordinateLabelsAsync()
        {
            if (!int.TryParse(CoordWkid, out var w)) return;
            try
            {
                var (geo, name) = await ProApi.CrsInfoAsync(w);
                CoordLabelX = geo ? "Longitude" : "Easting";
                CoordLabelY = geo ? "Latitude" : "Northing";
                CoordHint = geo ? $"{name}: order Longitude, Latitude; decimal degrees (east and north positive)"
                                : $"{name}: order Easting, Northing; metres";
            }
            catch { CoordHint = $"Coordinate system {w} is not recognised (SCN-009)."; }
        }

        public async Task ApplyCoordinatesAsync()
        {
            if (!ScenarioDoc.TryParseNumber(CoordX, out var x) || !ScenarioDoc.TryParseNumber(CoordY, out var y))
            { Status = $"Enter {CoordLabelX} and {CoordLabelY} as plain numbers, e.g. 180000.5 (SRC-002)."; return; }
            if (!int.TryParse(CoordWkid, out var w)) { Status = "Enter a coordinate system code such as 2039 (SCN-009)."; return; }
            Doc.SetSourceLocation("coords", x, y, w);
            await UpdateCoordinateLabelsAsync();
            Status = "Source set from coordinates.";
        }

        public void ShowSourceCoordinates()
        {
            if (Doc.GetDouble("source.x") is double x && Doc.GetDouble("source.y") is double y)
            {
                CoordX = x.ToString("0.######", CultureInfo.InvariantCulture);
                CoordY = y.ToString("0.######", CultureInfo.InvariantCulture);
                _cw = ((int?)Doc.GetDouble("source.input_wkid") ?? 2039).ToString();
                NotifyPropertyChanged(nameof(CoordWkid));
                _ = UpdateCoordinateLabelsAsync();
            }
        }

        // ---------------------------------------------------------------- called by the map tools
        public void SetSourceFromMap(double x, double y, int wkid)
        {
            Doc.SetSourceLocation("map", x, y, wkid);
            ShowSourceCoordinates();
            Status = $"Source placed at {x:0.###}, {y:0.###} (EPSG {wkid}).";
        }

        public void SetHeading(double deg)
        {
            deg = ((deg % 360) + 360) % 360;
            Doc.SetDouble("source.directivity.heading_deg", Math.Round(deg, 1));
            Fields.RefreshAll();
        }

        public void SetAreaPolygon(IEnumerable<double[]> ring, int wkid)
        {
            Doc.SetString("area.mode", "polygon");
            Doc.Set("area.rings", new JsonArray(StructureFactory.Ring(ring)));
            Doc.Set("area.input_wkid", JsonValue.Create(wkid));
            Doc.Set("area.layer", null);
            Status = "Analysis area drawn. Edit it with the Edit Vertices tool on the overlay, or draw again.";
        }

        public JsonObject AddStructure(JsonObject s)
        {
            s["name"] = Doc.UniqueName((string)s["name"]);
            Doc.AddStructure(s);
            RebuildStructures((string)s["id"]);
            OpenSection("structures");
            return s;
        }

        // ---------------------------------------------------------------- spectrum
        public async Task PasteSpectrumAsync(string text)
        {
            if (string.IsNullOrWhiteSpace(text)) { Status = "The clipboard is empty."; return; }
            ApplySpectrum(await PythonBridge.ParseSpectrumTextAsync(text));
        }

        public async Task ImportCsvAsync()
        {
            var dlg = new Microsoft.Win32.OpenFileDialog { Filter = "CSV or text (*.csv;*.txt)|*.csv;*.txt|All files|*.*", Title = "Import Lw spectrum" };
            if (dlg.ShowDialog() == true) ApplySpectrum(await PythonBridge.ParseSpectrumCsvAsync(dlg.FileName));
        }

        private void ApplySpectrum(JsonObject r)
        {
            var issues = Issue.List(r["issues"]);
            if (r["lw"] is JsonArray a && a.Count == 8)
            {
                for (int i = 0; i < 8; i++) { var v = a[i]; Doc.Set($"source.spectrum.lw[{i}]", v == null ? null : JsonValue.Create((double)v)); }
                Doc.SetString("source.spectrum.kind", "manual");
                Status = a.Any(v => v == null) ? "Spectrum read; empty bands stay missing." : "Spectrum read.";
            }
            else Status = issues.FirstOrDefault(i => i.Severity == "error")?.Text ?? "The values could not be read.";
        }

        public string ProfileName { get; set; }
        private string _selProfile;
        public string SelectedProfile { get => _selProfile; set { _selProfile = value; ProfileName ??= value; NotifyPropertyChanged(); } }

        public async Task SaveProfileAsync()
        {
            var name = string.IsNullOrWhiteSpace(ProfileName) ? SelectedProfile : ProfileName;
            var lw = string.Join(",", LwRows.Select(r => r.Text));
            var r = await PythonBridge.ProfilesAsync("save", name ?? "", lw);
            Status = (bool?)r["ok"] == true ? $"Profile '{name}' saved." : (string)r["error"];
            await RefreshListsAsync();
        }

        public async Task LoadProfileAsync()
        {
            if (string.IsNullOrEmpty(SelectedProfile)) return;
            var r = await PythonBridge.ProfilesAsync("load", SelectedProfile);
            if (r["lw"] is JsonArray a)
            {
                for (int i = 0; i < 8; i++) Doc.Set($"source.spectrum.lw[{i}]", a[i] == null ? null : JsonValue.Create((double)a[i]));
                Doc.SetString("source.spectrum.profile", SelectedProfile);
                Doc.SetString("source.spectrum.kind", "named profile");
            }
        }

        // ---------------------------------------------------------------- terrain
        private LayerItem _raster;
        public LayerItem SelectedRaster { get => _raster; set { _raster = value; NotifyPropertyChanged(); } }
        private string _dtmInfo = "No DTM selected: flat ground at 0 m";
        public string DtmInfoText { get => _dtmInfo; set { _dtmInfo = value; NotifyPropertyChanged(); } }
        private bool _needUnit;
        public bool NeedVerticalUnit { get => _needUnit; set { _needUnit = value; NotifyPropertyChanged(); } }
        public string[] VerticalUnits { get; } = { "m", "ft" };

        public string VerticalUnit
        {
            get => Doc.GetString("terrain.vertical_unit");
            set { Doc.SetString("terrain.vertical_unit", value); NotifyPropertyChanged(); }
        }

        public async Task UseRasterAsync()
        {
            if (SelectedRaster == null) return;
            await SetDtmAsync(ProApi.DataPath(SelectedRaster.Layer), SelectedRaster.Name);
        }

        /// <summary>DTM = the raster(s) of the active map's ground elevation surface (Contents > Elevation Surfaces > Ground).</summary>
        public async Task UseGroundSurfaceAsync()
        {
            var items = await ProApi.GroundSourcesAsync();
            Log.Write("GROUND sources: " + string.Join("; ", items.Select(i => i.Name + " -> " + (i.Path ?? i.Source ?? "?"))));
            if (items.Count == 0)
            {
                Status = "The active map has no ground elevation source (Contents > Elevation Surfaces > Ground is empty or there is no map). Add a DTM raster as the ground source, or use 'Use this raster' / 'Browse'.";
                return;
            }
            var local = items.Where(i => i.IsLocal).ToList();
            if (local.Count == 0)
            {
                Status = $"The ground of this map comes from a web elevation service ({items[0].Name}). NoiseBox reads a raster file: export the area you need (Raster Analysis tools: Extract by Rectangle / Copy Raster) and use it with 'Browse', or add a local DTM raster as the ground source.";
                DtmInfoText = Status;
                return;
            }
            var pick = local[0];
            await SetDtmAsync(pick.Path, pick.Name);
            Doc.SetString("terrain.dtm.origin", "map ground surface");
            DtmInfoText = "Map ground surface: " + DtmInfoText + (local.Count > 1 ? $"  (the ground has {local.Count} raster sources; the first, {pick.Name}, is used)" : "");
            Status = "DTM taken from the map's ground surface: " + pick.Name + ".";
        }

        public async Task BrowseDtmAsync()
        {
            var dlg = new ArcGIS.Desktop.Catalog.OpenItemDialog { Title = "Select DTM", MultiSelect = false, Filter = ArcGIS.Desktop.Catalog.ItemFilters.Rasters };
            if (dlg.ShowDialog() == true && dlg.Items.Any())
            {
                var p = dlg.Items.First().Path;
                await SetDtmAsync(p, Path.GetFileNameWithoutExtension(p));
            }
        }

        public async Task SetDtmAsync(string path, string name)
        {
            if (string.IsNullOrEmpty(path)) return;
            Doc.Set("terrain.dtm", new JsonObject { ["path"] = path, ["name"] = name });
            var r = await PythonBridge.DtmInfoAsync(path);
            if ((bool?)r["ok"] != true) { DtmInfoText = (string)r["error"]; return; }
            bool known = (bool?)r["unit_known"] ?? false;
            NeedVerticalUnit = !known && string.IsNullOrEmpty(VerticalUnit);
            DtmInfoText = $"{name}: native cell {(double)r["cell_m"]:0.##} m, {(string)r["crs_name"]} (EPSG {(int?)r["wkid"]}), " +
                          (known ? $"vertical unit {(string)r["unit_text"]}" : "vertical unit UNKNOWN: choose metres or feet (DTM-006)");
            Fields.RefreshAll();
        }

        public string CoverageText { get; private set; } = "";

        // ---------------------------------------------------------------- analysis area
        private LayerItem _polyLayer;
        public LayerItem SelectedPolygonLayer { get => _polyLayer; set { _polyLayer = value; NotifyPropertyChanged(); } }
        public bool UseSelectedPolygons { get; set; } = true;

        public async Task UsePolygonsAsync()
        {
            if (SelectedPolygonLayer?.Layer is not FeatureLayer fl) { Status = "Choose a polygon layer (ARA-007)."; return; }
            long n = await ProApi.SelectedCountAsync(fl);
            if (UseSelectedPolygons && n == 0) { Status = $"No polygon is selected in {fl.Name}. Select polygons, or choose the entire layer (ARA-006)."; return; }
            var (rings, wkid) = await ProApi.PolygonRingsAsync(fl, UseSelectedPolygons);
            if (rings.Count == 0) { Status = "The layer has no polygon geometry (ARA-002)."; return; }
            Doc.SetString("area.mode", "polygon");
            Doc.Set("area.rings", new JsonArray(rings.Select(r => (JsonNode)StructureFactory.Ring(r)).ToArray()));
            Doc.Set("area.input_wkid", JsonValue.Create(wkid));
            Doc.Set("area.layer", new JsonObject { ["path"] = ProApi.DataPath(fl), ["name"] = fl.Name });
            Doc.SetString("area.selection", UseSelectedPolygons ? "selected" : "all");
            Status = $"Analysis area: {rings.Count} polygon ring(s) from {fl.Name}.";
        }

        public async Task CaptureExtentAsync()
        {
            var e = await ProApi.MapExtentAsync();
            if (e == null) { Status = "Open a map view first."; return; }
            var (x0, y0, x1, y1, w) = e.Value;
            Doc.SetString("area.mode", "extent");
            Doc.Set("area.extent", new JsonArray(x0, y0, x1, y1));
            Doc.Set("area.input_wkid", JsonValue.Create(w));
            Status = "Map extent captured; it stays fixed when you pan or zoom (ARA-015).";
        }

        public void UseRadius()
        {
            Doc.SetString("area.mode", "radius");
            if (Doc.GetDouble("area.radius_m") == null) Doc.SetDouble("area.radius_m", 500);
            Fields.RefreshAll();
            Status = "Circle around the source; it follows the source if it moves (ARA-014).";
        }

        private string _gridText = "";
        public string GridText { get => _gridText; set { _gridText = value; NotifyPropertyChanged(); } }

        // ---------------------------------------------------------------- propagation
        private string _atmo = "";
        public string AtmosphereText { get => _atmo; set { _atmo = value; NotifyPropertyChanged(); } }

        public async Task ShowAtmosphereAsync()
        {
            Status = "Asking the MATLAB core for the absorption coefficients (starts MATLAB, 10-80 s) ...";
            var r = await PythonBridge.AtmosphereAsync(Doc);
            if ((bool?)r["ok"] != true) { Status = (string)r["error"]; return; }
            var a = (JsonArray)r["alpha_dB_per_km"];
            AtmosphereText = string.Join("   ", Bands.Select((b, i) => $"{b} Hz: {(double)a[i]:0.00}")) + "   (dB/km)";
            Status = "Atmospheric absorption coefficients updated.";
        }

        // ---------------------------------------------------------------- outputs
        public void BrowseGdb()
        {
            var dlg = new ArcGIS.Desktop.Catalog.OpenItemDialog { Title = "Output geodatabase", MultiSelect = false, Filter = ArcGIS.Desktop.Catalog.ItemFilters.Geodatabases };
            if (dlg.ShowDialog() == true && dlg.Items.Any()) { Doc.SetString("outputs.gdb", dlg.Items.First().Path); Fields.RefreshAll(); }
        }

        public bool OverallA { get => Doc.GetBool("outputs.overall_a", true); set { Doc.SetBool("outputs.overall_a", value); NotifyPropertyChanged(); } }
        public bool OverallZ { get => Doc.GetBool("outputs.overall_z"); set { Doc.SetBool("outputs.overall_z", value); NotifyPropertyChanged(); } }
        public bool AddToMap { get => Doc.GetBool("outputs.add_to_map", true); set { Doc.SetBool("outputs.add_to_map", value); NotifyPropertyChanged(); } }
        public bool LimitWeightA
        {
            get => Doc.GetString("outputs.limit_band_weighting") != "Z";
            set { Doc.SetString("outputs.limit_band_weighting", value ? "A" : "Z"); NotifyPropertyChanged(); NotifyPropertyChanged(nameof(LimitRuleText)); }
        }

        public string LimitRuleText
        {
            get
            {
                var parts = new List<string>();
                var ov = Doc.GetDouble("outputs.limit_dba");
                if (ov.HasValue) parts.Add($"LAeq <= {ov.Value:0.###} dB(A)");
                string unit = LimitWeightA ? "dB(A)" : "dB (unweighted)";
                foreach (var r in LimitRows) if (ScenarioDoc.TryParseNumber(r.Text, out var v)) parts.Add($"{r.Hz} Hz <= {v:0.###} {unit}");
                return parts.Count == 0 ? "No limit set: no margin or PASS/FAIL rasters are made."
                    : "A cell PASSES only if every limit is met: " + string.Join("; ", parts) + ". One exceeded band is enough to FAIL.";
            }
        }

        public void ClearLimits()
        {
            Doc.Set("outputs.limit_dba", null);
            for (int i = 0; i < 8; i++) Doc.Set($"outputs.limit_bands[{i}]", null);
            Fields.RefreshAll();
            foreach (var r in LimitRows) r.Refresh();
            NotifyPropertyChanged(nameof(LimitRuleText));
        }

        private string _engineText = "MATLAB engine: not checked. The first run starts MATLAB (about 10 s); it then stays ready for later runs and quits after 30 idle minutes.";
        public string EngineText { get => _engineText; set { _engineText = value; NotifyPropertyChanged(); } }

        /// <summary>Shows (or stops) the warm MATLAB engine. "warm" keeps one MATLAB ready between runs; "fresh" starts one per run.</summary>
        public async Task ShowEngineAsync(bool stop)
        {
            var r = await PythonBridge.EngineAsync(stop ? "stop" : "status");
            if ((bool?)r["ok"] != true) { EngineText = (string)r["error"] ?? "The engine status could not be read."; return; }
            string mode = (string)r["mode"] ?? "warm";
            if (mode == "fresh") { EngineText = "MATLAB mode: fresh (a new MATLAB for every run). Change it with \"engine\" in config.json."; return; }
            bool running = (bool?)r["running"] ?? false;
            EngineText = running
                ? $"MATLAB engine: ready ({(string)r["matlab_version"]}), {(int?)r["jobs"] ?? 0} run(s) served. It quits after {(double?)r["idle_minutes"] ?? 30:0} idle minutes."
                : (stop ? "MATLAB engine stopped; memory is free. The next run starts it again (about 10 s)." : "MATLAB engine: not running. The next run starts it (about 10 s), then it stays ready.");
        }

        public string[] DetailChoices { get; } = { "None", "Levels only", "Full" };
        public string Detail { get => Doc.GetString("outputs.detail"); set { Doc.SetString("outputs.detail", value); NotifyPropertyChanged(); } }

        /// <summary>Which octave-band rasters to save. Does not change the bands used for the overall results.</summary>
        public bool GetBand(int hz) => (Doc.Get("outputs.bands") as JsonArray)?.Any(b => (int)b == hz) ?? false;

        public void SetBand(int hz, bool on)
        {
            var bands = ((Doc.Get("outputs.bands") as JsonArray)?.Select(b => (int)b).ToList() ?? new List<int>());
            bands.Remove(hz);
            if (on) bands.Add(hz);
            Doc.Set("outputs.bands", new JsonArray(bands.OrderBy(b => b).Select(b => (JsonNode)b).ToArray()));
        }

        public ObservableCollection<BandChoice> BandChoices { get; } = new ObservableCollection<BandChoice>();

        // ---------------------------------------------------------------- map overlay
        private async Task RedrawOverlayAsync()
        {
            try
            {
                var pv = NoiseBoxModule.Current.LastPreview;
                Log.Write("REDRAW requested");
                bool layers = await InputLayers.SyncAsync(Doc, pv);
                await _overlay.DrawAsync(Doc, pv, SelectedId, SelectedFace, layers);
            }
            catch (Exception e) { Log.Write("REDRAW " + e); /* no active map view: nothing to draw on */ }
        }

        public async Task ZoomToSelectedAsync()
        {
            var pv = NoiseBoxModule.Current.LastPreview;
            var st = (pv?["structures"] as JsonArray)?.FirstOrDefault(s => (string)s["id"] == SelectedId);
            var ring = (st?["ring"] ?? st?["path"]) as JsonArray;
            int wkid = (int?)pv?["source"]?["wkid"] ?? 0;
            if (ring == null || wkid == 0) { Status = "Run Preview first so the object has a position."; return; }
            var sr = await QueuedTask.Run(() => ArcGIS.Core.Geometry.SpatialReferenceBuilder.CreateSpatialReference(wkid));
            var env = await QueuedTask.Run(() => ArcGIS.Core.Geometry.PolylineBuilderEx.CreatePolyline(
                ring.Select(p => new ArcGIS.Core.Geometry.Coordinate2D((double)p[0], (double)p[1])).ToList(), sr).Extent);
            await QueuedTask.Run(() => MapView.Active?.ZoomToAsync(env.Expand(1.5, 1.5, true)));
        }
    }

    internal sealed class BandChoice : PropertyChangedBase
    {
        private readonly NoiseBoxPaneViewModel _vm;
        public int Hz { get; }
        public BandChoice(NoiseBoxPaneViewModel vm, int hz) { _vm = vm; Hz = hz; }
        public bool Save { get => _vm.GetBand(Hz); set { _vm.SetBand(Hz, value); NotifyPropertyChanged(); } }
    }
}
