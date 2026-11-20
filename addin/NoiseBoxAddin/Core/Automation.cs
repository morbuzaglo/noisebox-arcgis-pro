using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Windows.Threading;
using ArcGIS.Desktop.Framework;
using NoiseBoxAddin.Buttons;

namespace NoiseBoxAddin.Core
{
    /// <summary>
    /// Test hook, OFF unless the environment variable NOISEBOX_AUTOMATION=1 is set when ArcGIS Pro starts. It lets the automated
    /// tests do what a finished map sketch does (the map tools only pass the finished geometry to the same pane methods), without
    /// taking over the user's mouse. Commands are JSON files %LOCALAPPDATA%\NoiseBox\automation\cmd_*.json; results are appended to
    /// automation.log in the same folder.
    ///   {"cmd":"place_source","x":..,"y":..,"wkid":..}        = a click with Place Source
    ///   {"cmd":"area_polygon","ring":[[x,y],..],"wkid":..}      = a finished Draw Analysis Area sketch
    ///   {"cmd":"set","path":"structures[0].vertical.value","value":4}   = the same as typing the value into the pane
    ///   {"cmd":"building"|"barrier"|"enclosure","points":[[x,y],..],"wkid":..}   = finished Building / Barrier / Enclosure sketches
    /// </summary>
    internal static class Automation
    {
        private static DispatcherTimer _timer;
        private static string Dir => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "NoiseBox", "automation");

        public static void Start()
        {
            if (Environment.GetEnvironmentVariable("NOISEBOX_AUTOMATION") != "1" || _timer != null) return;
            Directory.CreateDirectory(Dir);
            FrameworkApplication.Current.Dispatcher.BeginInvoke(new Action(() =>
            {
                _timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(700) };
                _timer.Tick += (s, e) => Poll();
                _timer.Start();
                Log.Write("AUTOMATION hook active (NOISEBOX_AUTOMATION=1)");
            }));
        }

        private static void Poll()
        {
            foreach (var f in Directory.GetFiles(Dir, "cmd_*.json").OrderBy(x => x))
            {
                string text = null;
                try { text = File.ReadAllText(f); File.Delete(f); } catch { continue; }
                string result;
                try { result = Execute(JsonNode.Parse(text).AsObject()); }
                catch (Exception ex) { result = "ERROR " + ex.Message; Log.Write("AUTOMATION " + ex); }
                File.AppendAllText(Path.Combine(Dir, "automation.log"), DateTime.Now.ToString("s") + "  " + Path.GetFileName(f) + "  " + result + Environment.NewLine);
            }
        }

        private static List<double[]> Pts(JsonNode a) => a.AsArray().Select(p => new[] { (double)p[0], (double)p[1] }).ToList();

        private static string Execute(JsonObject c)
        {
            var pane = Ui.Pane;
            if (pane == null) return "no pane";
            int w = (int?)c["wkid"] ?? 0;
            switch ((string)c["cmd"])
            {
                case "place_source": pane.SetSourceFromMap((double)c["x"], (double)c["y"], w); return "source placed";
                case "area_polygon": pane.SetAreaPolygon(Pts(c["ring"]), w); return "area set";
                case "building": pane.AddStructure(StructureFactory.Building("Building", Pts(c["points"]), w, null)); return "building added";
                case "barrier": pane.AddStructure(StructureFactory.Barrier("Barrier", Pts(c["points"]), w, null)); return "barrier added";
                case "enclosure": pane.AddStructure(StructureFactory.PolygonEnclosure("Enclosure", Pts(c["points"]), w, null)); return "enclosure added";
                case "set": pane.Doc.Set((string)c["path"], c["value"]?.DeepClone()); pane.RefreshAfterExternalChange(); return "set " + (string)c["path"];
                case "gp":
                {
                    // run a geoprocessing tool inside Pro (used by the tests, e.g. to start the MCP bridge): {"cmd":"gp","tool":"<toolbox>\<tool>","args":["a","b"]}
                    var args = c["args"] is JsonArray a ? a.Select(x => (object)(string)x).ToArray() : new object[0];
                    var t = ArcGIS.Desktop.Core.Geoprocessing.Geoprocessing.ExecuteToolAsync((string)c["tool"], ArcGIS.Desktop.Core.Geoprocessing.Geoprocessing.MakeValueArray(args));
                    t.ContinueWith(r =>
                    {
                        string txt = r.IsFaulted ? "FAULTED " + r.Exception?.GetBaseException().Message
                            : (r.Result.IsFailed ? "FAILED: " : "OK: ") + string.Join(" | ", r.Result.Messages.Select(m => m.Text).Where(x => !string.IsNullOrWhiteSpace(x)).Take(12));
                        File.AppendAllText(Path.Combine(Dir, "automation.log"), DateTime.Now.ToString("s") + "  gp result  " + txt + Environment.NewLine);
                    });
                    return "geoprocessing started";
                }
                case "zoom":
                {
                    var sr = ArcGIS.Core.Geometry.SpatialReferenceBuilder.CreateSpatialReference(w);
                    var env = ArcGIS.Core.Geometry.EnvelopeBuilderEx.CreateEnvelope((double)c["xmin"], (double)c["ymin"], (double)c["xmax"], (double)c["ymax"], sr);
                    ArcGIS.Desktop.Framework.Threading.Tasks.QueuedTask.Run(() => ArcGIS.Desktop.Mapping.MapView.Active?.ZoomTo(env, TimeSpan.Zero));
                    return "zoomed";
                }
                default: return "unknown command";
            }
        }
    }
}
