using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Globalization;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using System.Windows.Threading;
using ArcGIS.Core.CIM;
using ArcGIS.Core.Data;
using ArcGIS.Desktop.Framework;
using ArcGIS.Desktop.Framework.Contracts;
using ArcGIS.Desktop.Mapping;
using NoiseBoxAddin.Core;

namespace NoiseBoxAddin.UI
{
    /// <summary>A row of an octave-band table (Lw, Dc, TL or alpha). Empty text = missing value, not 0.</summary>
    internal sealed class BandRow : PropertyChangedBase
    {
        private readonly Func<ScenarioDoc> _doc;
        private readonly string _path;
        public int Hz { get; }
        public string Note { get; set; } = "";

        public BandRow(Func<ScenarioDoc> doc, string arrayPath, int index, int hz)
        {
            _doc = doc; _path = $"{arrayPath}[{index}]"; Hz = hz;
        }

        public string Text
        {
            get { var d = _doc().GetDouble(_path); return d.HasValue ? d.Value.ToString("0.###", CultureInfo.InvariantCulture) : ""; }
            set
            {
                if (string.IsNullOrWhiteSpace(value)) _doc().Set(_path, null);
                else if (ScenarioDoc.TryParseNumber(value, out var v)) _doc().SetDouble(_path, v);
                else _doc().SetString(_path, value);
                NotifyPropertyChanged(nameof(Text));
            }
        }

        public void Refresh() { NotifyPropertyChanged(nameof(Text)); NotifyPropertyChanged(nameof(Note)); }
    }

    internal sealed class StructureItem : PropertyChangedBase
    {
        private readonly ScenarioDoc _doc;
        public string Id { get; }
        public StructureItem(ScenarioDoc doc, string id) { _doc = doc; Id = id; }

        private JsonObject S => _doc.FindStructure(Id);
        public string Name => (string)S?["name"];
        public string Type => ((string)S?["type"]) switch { "building" => "Building", "barrier" => "Noise barrier", "enclosure" => "Enclosure", _ => "?" };

        /// <summary>Include in Analysis: whether the engine uses it.</summary>
        public bool Include
        {
            get => (bool?)S?["include"] ?? true;
            set { S["include"] = value; _doc.Touch(); NotifyPropertyChanged(nameof(Include)); NotifyPropertyChanged(nameof(State)); }
        }

        /// <summary>Visible: whether it is drawn on the map. Independent of Include.</summary>
        public bool Visible
        {
            get => (bool?)S?["visible"] ?? true;
            set { S["visible"] = value; _doc.Touch(); NotifyPropertyChanged(nameof(Visible)); NotifyPropertyChanged(nameof(State)); }
        }

        public string State => (Include ? "in the run" : "excluded from the run") + ", " + (Visible ? "drawn" : "hidden on the map");
    }

    internal partial class NoiseBoxPaneViewModel : DockPane
    {
        private const string PaneId = "NoiseBox_Pane";
        private readonly OverlayManager _overlay = new OverlayManager();
        private readonly DispatcherTimer _debounce = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(700) };

        public static NoiseBoxPaneViewModel Instance => FrameworkApplication.DockPaneManager.Find(PaneId) as NoiseBoxPaneViewModel;

        /// <summary>Opens the pane with one section expanded (ribbon buttons call this) and optionally focuses a field.</summary>
        public static void Show(string section, string focusKey = null)
        {
            var vm = FrameworkApplication.DockPaneManager.Find(PaneId) as NoiseBoxPaneViewModel;
            if (vm == null) return;
            vm.Activate();
            vm.OpenSection(section);
            if (focusKey != null) vm.FocusRequested?.Invoke(focusKey);
        }

        public event Action<string> FocusRequested;

        protected override Task InitializeAsync()
        {
            Doc.Changed += OnDocChanged;
            _debounce.Tick += async (s, e) => { _debounce.Stop(); await RefreshIssuesAsync(false); };
            RegisterFields();
            BuildCommands();
            BuildBandRows();
            RebuildStructures();
            RebuildMaterial();
            return RefreshListsAsync();
        }

        public ScenarioDoc Doc => NoiseBoxModule.Current.Doc;

        // ---------------------------------------------------------------- section expanders
        private readonly Dictionary<string, bool> _open = new Dictionary<string, bool>
        {
            ["scenario"] = true, ["source"] = true, ["terrain"] = false, ["structures"] = false, ["propagation"] = false, ["outputs"] = false, ["issues"] = true,
        };

        public bool OpenScenario { get => _open["scenario"]; set { _open["scenario"] = value; NotifyPropertyChanged(); } }
        public bool OpenSource { get => _open["source"]; set { _open["source"] = value; NotifyPropertyChanged(); } }
        public bool OpenTerrain { get => _open["terrain"]; set { _open["terrain"] = value; NotifyPropertyChanged(); } }
        public bool OpenStructures { get => _open["structures"]; set { _open["structures"] = value; NotifyPropertyChanged(); } }
        public bool OpenPropagation { get => _open["propagation"]; set { _open["propagation"] = value; NotifyPropertyChanged(); } }
        public bool OpenOutputs { get => _open["outputs"]; set { _open["outputs"] = value; NotifyPropertyChanged(); } }
        public bool OpenIssues { get => _open["issues"]; set { _open["issues"] = value; NotifyPropertyChanged(); } }

        /// <summary>Sections can be visited in any order; opening one never closes another.</summary>
        public void OpenSection(string section)
        {
            section = section == "area" ? "terrain" : section == "engine" ? "issues" : section;
            if (!_open.ContainsKey(section)) return;
            _open[section] = true;
            NotifyPropertyChanged("Open" + char.ToUpper(section[0]) + section.Substring(1));
        }

        // ---------------------------------------------------------------- summaries shown when a section is collapsed
        public string ScenarioSummary => Doc.GetString("name") + (Doc.Dirty ? " (unsaved)" : "");

        public string SourceSummary
        {
            get
            {
                var h = Doc.GetDouble("source.height_m");
                return Doc.GetDouble("source.x") == null ? "Not set" : $"{Doc.GetString("source.name")}, {Fmt(h)} m above ground";
            }
        }

        public string TerrainSummary
        {
            get
            {
                var dtm = Doc.GetString("terrain.dtm.name");
                string cell = Doc.GetString("area.cell.mode") == "match_dtm" ? "match DTM" : Fmt(Doc.GetDouble("area.cell.size_m")) + " m output cells";
                return $"{(dtm ?? "Flat ground")}, {cell}";
            }
        }

        public string StructuresSummary
        {
            get
            {
                var items = Doc.Structures.OfType<JsonObject>().ToList();
                int b = items.Count(s => (string)s["type"] == "building");
                int bar = items.Count(s => (string)s["type"] == "barrier" && ((bool?)s["include"] ?? true));
                int enc = items.Count(s => (string)s["type"] == "enclosure");
                var parts = new List<string>();
                if (b > 0) parts.Add($"{b} building{(b == 1 ? "" : "s")}");
                if (items.Any(s => (string)s["type"] == "barrier")) parts.Add($"{bar} active barrier{(bar == 1 ? "" : "s")}");
                if (enc > 0) parts.Add($"{enc} enclosure{(enc == 1 ? "" : "s")}");
                return parts.Count == 0 ? "None" : string.Join(", ", parts);
            }
        }

        public string PropagationSummary
        {
            get
            {
                string g = Doc.GetBool("propagation.ground.separate")
                    ? $"G {Fmt(Doc.GetDouble("propagation.ground.Gs"))}/{Fmt(Doc.GetDouble("propagation.ground.Gm"))}/{Fmt(Doc.GetDouble("propagation.ground.Gr"))}"
                    : $"G = {Fmt(Doc.GetDouble("propagation.ground.G"))}";
                string met = Doc.GetString("propagation.meteorology.method") == "long_term" ? "long-term" : "favourable";
                return $"{Doc.GetString("propagation.mode")}, {g}, {Fmt(Doc.GetDouble("propagation.atmosphere.T_C"))} °C, {Fmt(Doc.GetDouble("propagation.atmosphere.RH"))} % RH, {met}";
            }
        }

        public string OutputsSummary
        {
            get
            {
                string run = string.IsNullOrEmpty(Doc.GetString("outputs.run_name")) ? "Run name not set" : Doc.GetString("outputs.run_name");
                int nl = (Doc.GetDouble("outputs.limit_dba").HasValue ? 1 : 0) + LimitRows.Count(r => ScenarioDoc.TryParseNumber(r.Text, out _));
                return nl == 0 ? run : run + ", " + nl + " limit" + (nl == 1 ? "" : "s");
            }
        }

        private static string Fmt(double? v) => v.HasValue ? v.Value.ToString("0.###", CultureInfo.InvariantCulture) : "?";

        // ---------------------------------------------------------------- document changes
        private void OnDocChanged()
        {
            foreach (var n in new[] { nameof(ScenarioSummary), nameof(SourceSummary), nameof(TerrainSummary), nameof(StructuresSummary),
                                      nameof(PropagationSummary), nameof(OutputsSummary), nameof(UseMatchDtm), nameof(SeparateG), nameof(LongTerm),
                                      nameof(DirectionalMode), nameof(AreaModeText), nameof(ScreeningOn) })
                NotifyPropertyChanged(n);
            foreach (var r in LwRows.Concat(DcRows).Concat(LimitRows)) r.Refresh();
            NotifyPropertyChanged(nameof(LimitRuleText)); NotifyPropertyChanged(nameof(LimitWeightA));
            SpectrumVersion++;
            NotifyPropertyChanged(nameof(SpectrumVersion));
            _debounce.Stop();
            _debounce.Start();                                    // live, fast validation after the user pauses typing
            _ = RedrawOverlayAsync();
        }

        public void ReplaceDocument(ScenarioDoc doc)
        {
            Doc.Changed -= OnDocChanged;
            NoiseBoxModule.Current.Doc = doc;
            doc.Changed += OnDocChanged;
            Fields.RefreshAll();
            RebuildStructures();
            BuildBandRows();
            OnDocChanged();
        }

        public int SpectrumVersion { get; private set; }

        // ---------------------------------------------------------------- bound fields
        public FieldBag Fields { get; private set; }
        public FieldBag SF { get; private set; }         // fields of the selected structure

        private void RegisterFields()
        {
            Fields = new FieldBag(() => Doc);
            Fields.Str("name", "name");
            Fields.Str("sname", "source.name");
            Fields.Num("height", "source.height_m");
            Fields.Num("heading", "source.directivity.heading_deg");
            Fields.Num("radius", "area.radius_m");
            Fields.Num("cell", "area.cell.size_m");
            Fields.Num("rh", "area.receiver_height_m");
            Fields.Num("G", "propagation.ground.G");
            Fields.Num("Gs", "propagation.ground.Gs");
            Fields.Num("Gm", "propagation.ground.Gm");
            Fields.Num("Gr", "propagation.ground.Gr");
            Fields.Num("T", "propagation.atmosphere.T_C");
            Fields.Num("RHum", "propagation.atmosphere.RH");
            Fields.Num("P", "propagation.atmosphere.p_kPa");
            Fields.Num("C0", "propagation.meteorology.C0");
            Fields.Num("limit", "outputs.limit_dba");
            Fields.Str("gdb", "outputs.gdb");
            Fields.Str("run", "outputs.run_name");
            Fields.Num("smin", "outputs.shared_scale.min");
            Fields.Num("smax", "outputs.shared_scale.max");

            SF = new FieldBag(() => Doc);
            string P(string suffix) => SelectedId == null ? null : $"structures[{Doc.IndexOfStructure(SelectedId)}].{suffix}";
            SF.StrDyn("sname", () => P("name"));
            SF.NumDyn("bheight", () => P("height_m"));
            SF.NumDyn("vvalue", () => P("vertical.value"));
            SF.NumDyn("gap", () => P("gap_m"));
            SF.NumDyn("pstartx", () => P("placement.start[0]"));
            SF.NumDyn("pstarty", () => P("placement.start[1]"));
            SF.NumDyn("plen", () => P("placement.length_m"));
            SF.NumDyn("paz", () => P("placement.azimuth_deg"));
            SF.NumDyn("elen", () => P("rect.length_m"));
            SF.NumDyn("ewid", () => P("rect.width_m"));
            SF.NumDyn("ehei", () => P("height_m"));
            SF.NumDyn("eori", () => P("rect.orientation_deg"));
            SF.NumDyn("eox", () => P("rect.offset[0]"));
            SF.NumDyn("eoy", () => P("rect.offset[1]"));
            SF.NumDyn("eopen", () => P("open_area_m2"));
        }

        // ---------------------------------------------------------------- band tables (Lw, Dc)
        public ObservableCollection<BandRow> LwRows { get; } = new ObservableCollection<BandRow>();
        public ObservableCollection<BandRow> DcRows { get; } = new ObservableCollection<BandRow>();
        public ObservableCollection<BandRow> LimitRows { get; } = new ObservableCollection<BandRow>();
        public static readonly int[] Bands = { 63, 125, 250, 500, 1000, 2000, 4000, 8000 };

        private void BuildBandRows()
        {
            LwRows.Clear(); DcRows.Clear(); LimitRows.Clear(); Doc.EnsureDefaults();
            for (int i = 0; i < 8; i++)
            {
                LwRows.Add(new BandRow(() => Doc, "source.spectrum.lw", i, Bands[i]));
                DcRows.Add(new BandRow(() => Doc, "source.directivity.dc", i, Bands[i]));
                LimitRows.Add(new BandRow(() => Doc, "outputs.limit_bands", i, Bands[i]));
            }
        }

        public IEnumerable<double?> LwValues => LwRows.Select(r => ScenarioDoc.TryParseNumber(r.Text, out var v) ? v : (double?)null);

        // ---------------------------------------------------------------- directivity, propagation switches
        public bool DirectionalMode
        {
            get => Doc.GetString("source.directivity.mode") == "directional";
            set { Doc.SetString("source.directivity.mode", value ? "directional" : "omni"); NotifyPropertyChanged(); }
        }

        public bool UseMatchDtm
        {
            get => Doc.GetString("area.cell.mode") == "match_dtm";
            set { Doc.SetString("area.cell.mode", value ? "match_dtm" : "custom"); NotifyPropertyChanged(); }
        }

        public bool SeparateG
        {
            get => Doc.GetBool("propagation.ground.separate");
            set { Doc.SetBool("propagation.ground.separate", value); NotifyPropertyChanged(); }
        }

        public bool LongTerm
        {
            get => Doc.GetString("propagation.meteorology.method") == "long_term";
            set { Doc.SetString("propagation.meteorology.method", value ? "long_term" : "favourable"); NotifyPropertyChanged(); }
        }

        /// <summary>Terrain diffraction. Unchecking is reported as an error with a DTM: this engine version cannot keep
        /// terrain elevations while switching terrain screening off (issue DTM-016).</summary>
        public bool ScreeningOn
        {
            get => Doc.GetBool("terrain.screening", true);
            set { Doc.SetBool("terrain.screening", value); NotifyPropertyChanged(); }
        }

        public string[] Modes { get; } = { "iso2024", "draft2026", "iso1996" };

        public string Mode
        {
            get => Doc.GetString("propagation.mode");
            set { Doc.SetString("propagation.mode", value); NotifyPropertyChanged(); NotifyPropertyChanged(nameof(ModeText)); }
        }

        public string ModeText => Mode switch
        {
            "iso2024" => "ISO 9613-2:2024 – prediction mode: iso2024 (default)",
            "draft2026" => "Draft amendment to ISO 9613-2:2024 – not a published edition",
            "iso1996" => "ISO 9613-2:1996 – superseded edition",
            _ => Mode,
        };

        public string AreaModeText => Doc.GetString("area.mode") switch
        {
            "polygon" => "Receiver polygon (" + ((Doc.Get("area.rings") as JsonArray)?.Count ?? 0) + " ring(s))",
            "radius" => $"Circle of {Fmt(Doc.GetDouble("area.radius_m"))} m around the source (follows the source)",
            "extent" => "Captured map extent (fixed)",
            _ => "No analysis area",
        };

        // ---------------------------------------------------------------- lists from the open map
        public ObservableCollection<LayerItem> PointLayers { get; } = new ObservableCollection<LayerItem>();
        public ObservableCollection<LayerItem> PolygonLayers { get; } = new ObservableCollection<LayerItem>();
        public ObservableCollection<LayerItem> RasterLayers { get; } = new ObservableCollection<LayerItem>();
        public ObservableCollection<LayerItem> PolylineLayers { get; } = new ObservableCollection<LayerItem>();

        public async Task RefreshListsAsync()
        {
            Fill(PointLayers, await ProApi.LayersAsync(esriGeometryType.esriGeometryPoint));
            Fill(PolygonLayers, await ProApi.LayersAsync(esriGeometryType.esriGeometryPolygon));
            Fill(PolylineLayers, await ProApi.LayersAsync(esriGeometryType.esriGeometryPolyline));
            Fill(RasterLayers, await ProApi.RasterLayersAsync());
            Profiles.Clear();
            var p = await PythonBridge.ProfilesAsync("list");
            if (p["profiles"] is JsonArray a) foreach (var n in a) Profiles.Add((string)n);
        }

        private static void Fill(ObservableCollection<LayerItem> target, List<LayerItem> items)
        {
            target.Clear();
            foreach (var i in items) target.Add(i);
        }

        public ObservableCollection<string> Profiles { get; } = new ObservableCollection<string>();

        // ---------------------------------------------------------------- status line
        private string _status = "Ready";
        public string Status { get => _status; set { _status = value; NotifyPropertyChanged(); } }
    }
}
