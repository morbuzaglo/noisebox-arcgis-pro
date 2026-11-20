using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using ArcGIS.Core.CIM;
using ArcGIS.Desktop.Framework.Threading.Tasks;
using ArcGIS.Desktop.Mapping;

namespace NoiseBoxAddin.Core
{
    /// <summary>
    /// Adds the results of a run to the active map with the Pro SDK. The geoprocessing tool normally does this itself (named group,
    /// styled layers); when Pro refuses it inside the tool ("Failed to add data"), the tool says so and this class adds the same
    /// datasets afterwards, so a finished run always ends up in Contents.
    /// </summary>
    internal static class ResultLayers
    {
        private static CIMColor C(int r, int g, int b) => ColorFactory.Instance.CreateRGBColor(r, g, b);

        private static CIMColorRamp LevelRamp() => new CIMMultipartColorRamp
        {
            ColorRamps = new CIMColorRamp[]
            {
                new CIMLinearContinuousColorRamp { FromColor = C(0, 150, 80), ToColor = C(255, 230, 0) },
                new CIMLinearContinuousColorRamp { FromColor = C(255, 230, 0), ToColor = C(200, 0, 0) },
            },
        };

        private static string Label(string key)
        {
            if (key.StartsWith("Lp")) return "Lp " + key.Substring(2) + " Hz, dB (unweighted)";
            return key switch
            {
                "laeq" => "LAeq dB(A)", "lz" => "Overall unweighted level, dB", "margin" => "Margin to limit (dB, + = exceeds)",
                "passfail" => "Limit check (PASS = 1 / FAIL = 0)", "cells" => "Detail cells: click a cell to read all values", _ => key,
            };
        }

        /// <summary>created: key -> dataset path, as printed by the tool ("Created: laeq=..., margin=...").</summary>
        public static Task<int> AddAsync(string scenarioName, string run, Dictionary<string, string> created) => QueuedTask.Run(() =>
        {
            var map = MapView.Active?.Map;
            if (map == null) return 0;
            var group = LayerFactory.Instance.CreateGroupLayer(map, 0, $"NoiseBox: {scenarioName} | {run}");
            int n = 0;
            var order = new[] { "cells", "passfail", "margin", "lz" }.Concat(created.Keys.Where(k => k.StartsWith("Lp")).OrderByDescending(k => k)).Concat(new[] { "laeq" });
            foreach (var key in order)                                           // each new layer goes on top: LAeq ends up on top
            {
                if (!created.TryGetValue(key, out var path) || string.IsNullOrEmpty(path)) continue;
                path = Path.GetFullPath(path.Replace("\\\\", "\\"));
                try
                {
                    string label = Label(key);
                    bool visible = key == "laeq" || key == "passfail";
                    if (key == "cells")
                    {
                        var fp = new FeatureLayerCreationParams(new Uri(path)) { Name = label, IsVisible = true };
                        LayerFactory.Instance.CreateLayer<FeatureLayer>(fp, group);
                    }
                    else
                    {
                        var rp = new RasterLayerCreationParams(new Uri(path)) { Name = label, IsVisible = visible };
                        if (key != "passfail") rp.ColorizerDefinition = new StretchColorizerDefinition(0, RasterStretchType.MinimumMaximum, 1.0, LevelRamp());
                        LayerFactory.Instance.CreateLayer<RasterLayer>(rp, group);
                    }
                    n++;
                }
                catch (Exception e) { Log.Write("RESULT LAYER " + key + ": " + e.Message); }
            }
            return n;
        });

        public static Dictionary<string, string> ParseCreated(IEnumerable<string> messages)
        {
            var d = new Dictionary<string, string>();
            var line = messages.FirstOrDefault(m => m != null && m.TrimStart().StartsWith("Created:"));
            if (line == null) return d;
            foreach (var part in line.Substring(line.IndexOf(':') + 1).Split(new[] { ", " }, StringSplitOptions.RemoveEmptyEntries))
            {
                int i = part.IndexOf('=');
                if (i > 0) d[part.Substring(0, i).Trim()] = part.Substring(i + 1).Trim();
            }
            return d;
        }

        public static string ParseRunName(IEnumerable<string> messages)
        {
            var line = messages.FirstOrDefault(m => m != null && m.TrimStart().StartsWith("Done:"));
            return line == null ? "run" : line.Substring(line.IndexOf(':') + 1).Trim();
        }
    }
}
