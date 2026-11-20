using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using ArcGIS.Desktop.Framework;
using ArcGIS.Desktop.Framework.Contracts;
using ArcGIS.Desktop.Framework.Threading.Tasks;
using NoiseBoxAddin.Core;

namespace NoiseBoxAddin.UI
{
    internal sealed class ProfilePoint
    {
        public double S { get; set; }
        public double? Ground { get; set; }
        public double Top { get; set; }
    }

    internal partial class NoiseBoxPaneViewModel
    {
        // ---------------------------------------------------------------- structures list
        public ObservableCollection<StructureItem> Items { get; } = new ObservableCollection<StructureItem>();
        public string SelectedId { get; private set; }
        public string SelectedFace { get; private set; }

        private StructureItem _selected;
        public StructureItem SelectedItem
        {
            get => _selected;
            set
            {
                _selected = value;
                SelectedId = value?.Id;
                SelectedFace = null;
                NotifyPropertyChanged();
                OnSelectionChanged();
            }
        }

        /// <summary>After the scenario was changed from outside the pane (the test hook): refresh every bound field and the list.</summary>
        public void RefreshAfterExternalChange()
        {
            Fields.RefreshAll();
            SF.RefreshAll();
            RebuildStructures(SelectedId);
            OnDocChanged();
        }

        public void RebuildStructures(string selectId = null)
        {
            var keep = selectId ?? SelectedId;
            Items.Clear();
            foreach (var s in Doc.Structures.OfType<JsonObject>()) Items.Add(new StructureItem(Doc, (string)s["id"]));
            SelectedItem = Items.FirstOrDefault(i => i.Id == keep);
            NotifyPropertyChanged(nameof(StructuresSummary));
            BandChoices.Clear();
            foreach (var b in Bands) BandChoices.Add(new BandChoice(this, b));
        }

        /// <summary>Selecting on the map opens the object's properties in the pane.</summary>
        public void SelectStructure(string id)
        {
            OpenSection("structures");
            SelectedItem = Items.FirstOrDefault(i => i.Id == id);
        }

        private string Prefix => SelectedId == null ? null : $"structures[{Doc.IndexOfStructure(SelectedId)}]";
        private string SelType => SelectedId == null ? null : (string)Doc.FindStructure(SelectedId)?["type"];
        public bool IsBuilding => SelType == "building";
        public bool IsBarrier => SelType == "barrier";
        public bool IsEnclosure => SelType == "enclosure";
        public bool HasSelection => SelectedId != null;
        public bool IsStraightBarrier => IsBarrier && Doc.GetString(Prefix + ".placement.mode") == "straight";

        private void OnSelectionChanged()
        {
            foreach (var n in new[] { nameof(IsBuilding), nameof(IsBarrier), nameof(IsEnclosure), nameof(HasSelection), nameof(IsStraightBarrier),
                                      nameof(BarrierRelative), nameof(TransmissionEnabled), nameof(VerticalLabel), nameof(SeparateFaces),
                                      nameof(ShowAlpha), nameof(MatIsMassLaw), nameof(MaterialNote), nameof(MatVisible) })
                NotifyPropertyChanged(n);
            SF.RefreshAll();
            RebuildFaceList();
            RebuildMaterial();
            _ = RedrawOverlayAsync();
        }

        // ---------------------------------------------------------------- barrier
        /// <summary>Vertical definition 1: constant height above local terrain (relative). 2: fixed absolute top elevation.</summary>
        public bool BarrierRelative
        {
            get => IsBarrier && Doc.GetString(Prefix + ".vertical.mode") != "absolute";
            set { Doc.SetString(Prefix + ".vertical.mode", value ? "relative" : "absolute"); NotifyPropertyChanged(); NotifyPropertyChanged(nameof(VerticalLabel)); }
        }

        public string VerticalLabel => BarrierRelative ? "Height above local terrain (m)" : "Top elevation, absolute (m above the DTM datum)";

        /// <summary>Diffraction only, or diffraction plus transmission through the barrier (needs material data).</summary>
        public bool TransmissionEnabled
        {
            get => IsBarrier && Doc.GetBool(Prefix + ".transmission.enabled");
            set
            {
                Doc.SetBool(Prefix + ".transmission.enabled", value);
                if (value && Doc.Get(Prefix + ".transmission.material") == null) Doc.Set(Prefix + ".transmission.material", StructureFactory.EmptyMaterial());
                NotifyPropertyChanged(); NotifyPropertyChanged(nameof(MaterialNote)); NotifyPropertyChanged(nameof(MatVisible)); RebuildMaterial();
            }
        }

        public ObservableCollection<ProfilePoint> ProfileData { get; } = new ObservableCollection<ProfilePoint>();
        public string ProfileNote { get; private set; } = "";

        /// <summary>Ground and barrier top along the barrier (DTM sampled by Python), to check what was defined.</summary>
        public async Task BarrierProfileAsync()
        {
            var r = await PythonBridge.OnScenarioAsync("barrier-profile", Doc, SelectedId);
            ProfileData.Clear();
            if ((bool?)r["ok"] != true) { Status = (string)r["error"]; return; }
            foreach (var p in (JsonArray)r["profile"])
                ProfileData.Add(new ProfilePoint { S = (double)p["s"], Ground = (double?)p["ground"], Top = (double)p["top"] });
            ProfileNote = BarrierRelative ? $"Flat top at {(double)r["flat_top"]:0.00} m (highest ground under the barrier + height; the engine uses a flat top per segment)."
                                          : $"Top at {(double)r["flat_top"]:0.00} m (absolute).";
            NotifyPropertyChanged(nameof(ProfileNote));
        }

        // ---------------------------------------------------------------- enclosure faces and materials
        public ObservableCollection<string> FaceNames { get; } = new ObservableCollection<string>();

        public string SelectedFaceName
        {
            get => SelectedFace;
            set { SelectedFace = value; NotifyPropertyChanged(); RebuildMaterial(); _ = RedrawOverlayAsync(); }
        }

        public bool SeparateFaces
        {
            get => IsEnclosure && Doc.GetString(Prefix + ".faces.mode") == "per_face";
            set { _ = SetSeparateFacesAsync(value); }
        }

        private async Task SetSeparateFacesAsync(bool on)
        {
            if (!IsEnclosure) return;
            await RefreshIssuesAsync(false);
            var faces = FaceNames.ToList();
            if (on)
            {
                var all = Doc.Get(Prefix + ".faces.all")?.ToJsonString();
                foreach (var f in faces) Doc.Set(Prefix + ".faces.faces." + f, JsonNode.Parse(all));      // start from the common material
                Doc.SetString(Prefix + ".faces.mode", "per_face");
                SelectedFace = faces.FirstOrDefault();
            }
            else { Doc.SetString(Prefix + ".faces.mode", "single"); SelectedFace = null; }
            NotifyPropertyChanged(nameof(SeparateFaces)); NotifyPropertyChanged(nameof(SelectedFaceName));
            RebuildMaterial();
            await RedrawOverlayAsync();
        }

        private void RebuildFaceList()
        {
            FaceNames.Clear();
            var st = (NoiseBoxModule.Current.LastPreview?["structures"] as JsonArray)?.FirstOrDefault(s => (string)s["id"] == SelectedId);
            if (st?["faces"] is JsonArray fa) foreach (var f in fa) FaceNames.Add((string)f["name"]);
        }

        private string MaterialPath
        {
            get
            {
                if (SelectedId == null) return null;
                if (IsBarrier) return Prefix + ".transmission.material";
                if (!IsEnclosure) return null;
                return SeparateFaces && SelectedFace != null ? Prefix + ".faces.faces." + SelectedFace : Prefix + ".faces.all";
            }
        }

        public bool ShowAlpha => IsEnclosure;                      // a barrier needs TL only; alpha belongs to the enclosure interior
        public bool MatVisible => MaterialPath != null && (IsEnclosure || TransmissionEnabled);
        public FieldBag MF { get; private set; }
        public ObservableCollection<BandRow> TlRows { get; } = new ObservableCollection<BandRow>();
        public ObservableCollection<BandRow> AlphaRows { get; } = new ObservableCollection<BandRow>();

        public bool MatIsMassLaw
        {
            get => MaterialPath != null && Doc.GetString(MaterialPath + ".mode") != "manufacturer";
            set
            {
                if (MaterialPath == null) return;
                Doc.SetString(MaterialPath + ".mode", value ? "mass_law" : "manufacturer");
                NotifyPropertyChanged(); NotifyPropertyChanged(nameof(MaterialNote));
            }
        }

        public bool MatSolid
        {
            get => MaterialPath != null && Doc.GetBool(MaterialPath + ".solid", true);
            set { Doc.SetBool(MaterialPath + ".solid", value); NotifyPropertyChanged(); }
        }

        /// <summary>Says whether the TL of the selected material is measured (manufacturer data) or estimated (mass law).</summary>
        public string MaterialNote =>
            MaterialPath == null ? "" :
            MatIsMassLaw ? "Estimated: mass law (core nb_material), a rough estimate, not a measurement."
                         : "Measured: manufacturer octave-band TL as entered. Empty bands are missing, not 0 dB.";

        private void RebuildMaterial()
        {
            MF = new FieldBag(() => Doc);
            MF.NumDyn("mass", () => MaterialPath == null ? null : MaterialPath + ".surface_mass_kg_m2");
            MF.NumDyn("thick", () => MaterialPath == null ? null : MaterialPath + ".thickness_m");
            MF.NumDyn("rho", () => MaterialPath == null ? null : MaterialPath + ".volume_density_kg_m3");
            NotifyPropertyChanged(nameof(MF));
            TlRows.Clear(); AlphaRows.Clear();
            if (MaterialPath != null && Doc.Get(MaterialPath) != null)
                for (int i = 0; i < 8; i++)
                {
                    TlRows.Add(new BandRow(() => Doc, MaterialPath + ".TL", i, Bands[i]));
                    AlphaRows.Add(new BandRow(() => Doc, MaterialPath + ".alpha", i, Bands[i]));
                }
            foreach (var n in new[] { nameof(MatIsMassLaw), nameof(MatSolid), nameof(MaterialNote), nameof(ShowAlpha) }) NotifyPropertyChanged(n);
            MaterialPreviewText = "";
        }

        private string _matPreview = "";
        public string MaterialPreviewText { get => _matPreview; set { _matPreview = value; NotifyPropertyChanged(); } }

        /// <summary>Transmission loss per octave band as the MATLAB core resolves it (mass law or measured).</summary>
        public async Task EstimateMaterialAsync()
        {
            if (MaterialPath == null) return;
            Status = "Asking the MATLAB core for the transmission loss (starts MATLAB, 10-80 s) ...";
            var r = await PythonBridge.MaterialAsync(Doc.Get(MaterialPath));
            if ((bool?)r["ok"] != true) { MaterialPreviewText = (string)r["error"]; Status = "The core rejected the material."; return; }
            var tl = (JsonArray)r["TL"];
            MaterialPreviewText = string.Join("   ", Bands.Select((b, i) => $"{b} Hz: {(double)tl[i]:0.0}")) + $"  dB TL ({(string)r["source"]}; {(string)r["confidence"]})";
            Status = "Transmission loss updated.";
        }

        // ---------------------------------------------------------------- issues, preview, run
        public ObservableCollection<Issue> Issues { get; } = new ObservableCollection<Issue>();
        public Issue SelectedIssue { get; set; }
        private string _issueSummary = "";
        public string IssueSummary { get => _issueSummary; set { _issueSummary = value; NotifyPropertyChanged(); } }
        private string _effects = "";
        public string EffectsText { get => _effects; set { _effects = value; NotifyPropertyChanged(); } }
        private string _elev = "";
        public string ElevationText { get => _elev; set { _elev = value; NotifyPropertyChanged(); } }
        private string _analysis = "";
        public string AnalysisCoordText { get => _analysis; set { _analysis = value; NotifyPropertyChanged(); } }
        private string _example = "";
        public string ExampleNames { get => _example; set { _example = value; NotifyPropertyChanged(); } }

        /// <summary>Preview: no acoustic calculation. deep = also reads the DTM (coverage, source elevation) and the output gdb.</summary>
        public async Task RefreshIssuesAsync(bool deep)
        {
            if (deep) Status = "Checking the scenario ...";
            var r = await PythonBridge.PreviewAsync(Doc, fast: !deep);
            if (r["issues"] == null) { Status = (string)r["error"] ?? "Preview failed."; return; }
            NoiseBoxModule.Current.LastPreview = r;
            Issues.Clear();
            foreach (var i in Issue.List(r["issues"])) Issues.Add(i);
            int e = Issues.Count(i => i.Severity == "error"), w = Issues.Count(i => i.Severity == "warning");
            IssueSummary = $"{e} error{(e == 1 ? "" : "s")}, {w} warning{(w == 1 ? "" : "s")}";
            EffectsText = r["effects"] is JsonArray ef ? string.Join("; ", ef.Select(x => (string)x)) : "";
            var g = r["grid"];
            GridText = g == null ? "" : $"About {(int)g["cells"]:N0} receiver cells ({(int)g["nx"]} x {(int)g["ny"]}) of {(double)g["cell"]:0.##} m";
            var el = r["elevation"];
            ElevationText = el == null ? (Doc.GetString("terrain.dtm.path") == null ? "No DTM yet: elevation is added when terrain is selected." : "")
                : $"Ground {(double)el["ground_m"]:0.00} m + height {(double)el["height_m"]:0.00} m = {(double)el["absolute_m"]:0.00} m absolute";
            var src = r["source"];
            AnalysisCoordText = src == null ? "" : $"Analysis system EPSG {(int)src["wkid"]}: {(double)src["x"]:0.###}, {(double)src["y"]:0.###}";
            ExampleNames = Issues.FirstOrDefault(i => i.Code == "OUT-011")?.Message ?? "";
            var cov = r["coverage"];
            CoverageText = cov == null ? "" : $"DTM: {(double)cov["pct_area_missing"]:0.#} % of the receiver area has no data; {(int)cov["n_paths_with_gaps"]} of {(int)cov["n_paths"]} paths cross gaps (red squares).";
            if (deep) Status = $"Preview: {IssueSummary}. {CoverageText}";
            RebuildFaceList();
            NotifyPropertyChanged(nameof(SourceSummary));
            await RedrawOverlayAsync();
        }

        public async Task RunAsync()
        {
            await RefreshIssuesAsync(true);
            var errors = Issues.Where(i => i.Severity == "error").ToList();
            if (errors.Count > 0)
            {
                OpenIssues = true;
                Status = $"{errors.Count} error(s) stop the run. Click one to go straight to the input. First: {errors[0].Message}";
                return;
            }
            Status = "Calculating: MATLAB starts first (10-80 s) ...";
            var cps = new CancelableProgressorSource("NoiseBox: calculating", "Cancelled");
            var (ok, msgs) = await ProApi.RunAsync(Doc, cps, m => { if (!string.IsNullOrWhiteSpace(m)) Status = m; });
            Status = ok ? $"Finished. Results are in Contents, group 'NoiseBox: {Doc.GetString("name")} | {Doc.GetString("outputs.run_name")}'."
                        : "The run failed: " + (msgs.LastOrDefault(m => m.Contains("ERROR") || m.Contains("Error")) ?? msgs.LastOrDefault());
        }

        /// <summary>Clicking an issue opens the section, selects the object it is about and focuses the field.</summary>
        public void GoTo(Issue i)
        {
            OpenSection(i.Section);
            if (!string.IsNullOrEmpty(i.ObjectId)) SelectStructure(i.ObjectId);
            var key = FocusKeyFor(i);
            if (key != null) FocusRequested?.Invoke(key);
        }

        private static string FocusKeyFor(Issue i)
        {
            var c = i.Code;
            if (c.StartsWith("SPC")) return "lw";
            if (c == "SRC-001" || c == "SRC-002" || c == "SRC-003" || c == "SRC-004") return "coordX";
            if (c.StartsWith("SRC")) return "height";
            if (c.StartsWith("DIR")) return "heading";
            if (c == "DTM-006") return "vunit";
            if (c.StartsWith("DTM")) return "dtm";
            if (c == "ARA-008") return "radius";
            if (c == "ARA-016" || c == "ARA-017") return "cell";
            if (c == "ARA-022" || c == "ARA-023") return "rh";
            if (c.StartsWith("ARA")) return "area";
            if (c.StartsWith("STR") || c.StartsWith("BLD") || c.StartsWith("BAR") || c.StartsWith("ENC")) return "sname";
            switch (c)
            {
                case "PRP-001": case "PRP-002": return "G";
                case "PRP-005": return "T";
                case "PRP-006": case "PRP-009": return "RHum";
                case "PRP-007": case "PRP-008": return "P";
                case "PRP-015": case "PRP-016": case "PRP-017": case "PRP-019": return "C0";
                case "OUT-001": case "OUT-002": case "OUT-003": case "OUT-004": return "gdb";
                case "OUT-005": case "OUT-006": return "run";
                case "OUT-012": return "smin";
                case "OUT-014": return "limit";
            }
            return null;
        }
    }
}
