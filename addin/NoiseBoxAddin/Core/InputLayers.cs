using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using ArcGIS.Core.CIM;
using ArcGIS.Core.Data;
using ArcGIS.Core.Data.DDL;
using DdlField = ArcGIS.Core.Data.DDL.FieldDescription;
using ArcGIS.Core.Geometry;
using ArcGIS.Desktop.Core;
using ArcGIS.Desktop.Framework.Threading.Tasks;
using ArcGIS.Desktop.Mapping;

namespace NoiseBoxAddin.Core
{
    /// <summary>
    /// Real GIS objects for everything the user creates with the tools: the source point, the noise barriers, buildings,
    /// enclosures and the receiver area are written to feature classes in the file geodatabase NoiseBox_inputs.gdb (next to the
    /// project) and added to Contents as the group "NoiseBox inputs". They stay on the map, can be selected, labelled, edited
    /// with Pro's own tools and zoomed to. The scenario file stays the master: the feature classes are rebuilt from it after
    /// every change, so they never drift away from what the calculation will use.
    /// "Drawn on map" off = the object is not written (not drawn); "Include in Analysis" is stored in the Include field.
    /// </summary>
    internal static class InputLayers
    {
        public const string GroupName = "NoiseBox inputs";
        public const string GdbName = "NoiseBox_inputs.gdb";
        private static bool _running, _pending, _dirty;
        private static string _lastSig;

        /// <summary>Forget what was written (new scenario opened, layers deleted): the next sync rebuilds everything.</summary>
        public static void Invalidate() { _lastSig = null; _dirty = false; }
        public static string LastError { get; private set; }

        private sealed class Row
        {
            public Geometry Shape;
            public Dictionary<string, object> Attr = new Dictionary<string, object>();
        }

        private sealed class Spec
        {
            public string Fc, Label;
            public GeometryType Type;
            public List<Row> Rows = new List<Row>();
            public Func<CIMSymbolReference> Symbol;
        }

        /// <summary>Brings the feature classes and layers in line with the scenario. Calls made while one is running are merged.</summary>
        public static async Task<bool> SyncAsync(ScenarioDoc doc, JsonObject preview)
        {
            string sig = (doc.Root["source"]?.ToJsonString() ?? "") + "|" + (doc.Root["area"]?.ToJsonString() ?? "") + "|" +
                         (doc.Root["structures"]?.ToJsonString() ?? "") + "|" + (preview?["source"]?.ToJsonString() ?? "") + "|" + (preview?["area"]?.ToJsonString() ?? "");
            if (sig == _lastSig && !_dirty) return true;
            _lastSig = sig;
            _pending = true;
            if (_running) return true;
            _running = true;
            bool ok = true;
            try
            {
                while (_pending)
                {
                    _pending = false;
                    ok = await QueuedTask.Run(() => SyncCore(doc, preview));
                }
            }
            catch (Exception e)
            {
                LastError = e.Message;
                Log.Write("INPUT LAYERS " + e);
                ok = false;
            }
            finally { _running = false; }
            return ok;
        }

        private static CIMColor C(int r, int g, int b, int a = 255) => ColorFactory.Instance.CreateRGBColor(r, g, b, a);

        private static string _gdbName = GdbName;

        private static bool SyncCore(ScenarioDoc doc, JsonObject preview, bool retry = true)
        {
            var mv = MapView.Active;
            var map = mv?.Map;
            if (map == null || Project.Current == null) { Log.Write("SYNC skipped: no active map view"); return false; }
            int mapWkid = ProApi.Wkid(map.SpatialReference);
            int wkid = (int?)preview?["source"]?["wkid"] ?? (int?)doc.Root["source"]?["input_wkid"] ?? mapWkid;
            if (wkid == 0) wkid = mapWkid;
            if (wkid == 0) return false;
            var sr = SpatialReferenceBuilder.CreateSpatialReference(wkid);

            var specs = BuildSpecs(doc, preview, sr, wkid);
            bool any = specs.Any(s => s.Rows.Count > 0);
            Log.Write("SYNC start: wkid " + wkid + ", rows " + string.Join(",", specs.Select(s => s.Fc + "=" + s.Rows.Count)));
            string gdbPath = Path.Combine(Project.Current.HomeFolderPath, _gdbName);
            if (!any && !Directory.Exists(gdbPath)) return true;                     // nothing to show yet, nothing to create

            var conn = new FileGeodatabaseConnectionPath(new Uri(gdbPath));
            if (!Directory.Exists(gdbPath)) SchemaBuilder.CreateGeodatabase(conn);
            // 0. layers of this group keep a schema lock on their feature classes: when the classes have to be replaced or created,
            //    take the group out of the map first (it is rebuilt below), otherwise the schema change fails
            bool needsSchema;
            using (var g0 = new Geodatabase(conn))
            {
                var ex0 = g0.GetDefinitions<FeatureClassDefinition>().ToDictionary(d => d.GetName(), d => d);
                needsSchema = any && specs.Any(sp => !ex0.TryGetValue(sp.Fc, out var d0) || ProApi.Wkid(d0.GetSpatialReference()) != wkid ||
                                                     d0.GetShapeType() != sp.Type || !d0.GetFields().Any(f => f.Name == "Include"));
            }
            if (needsSchema)
            {
                foreach (var old in map.GetLayersAsFlattenedList().OfType<GroupLayer>().Where(g => g.Name == GroupName).ToList()) map.RemoveLayer(old);
                GC.Collect(); GC.WaitForPendingFinalizers();
                System.Threading.Thread.Sleep(500);
                Log.Write("SYNC schema change: input layers removed from the map and rebuilt");
            }

            try
            {
                // 1. feature classes that exist with another coordinate system / layout are deleted first (a separate schema step:
                //    deleting and creating the same name in one step fails with "already exists")
                using (var gdb = new Geodatabase(conn))
                {
                    var existing = gdb.GetDefinitions<FeatureClassDefinition>().ToDictionary(d => d.GetName(), d => d);
                    var del = new SchemaBuilder(gdb);
                    bool anyDelete = false;
                    foreach (var s in specs)
                    {
                        if (!existing.TryGetValue(s.Fc, out var def)) continue;
                        int dw = ProApi.Wkid(def.GetSpatialReference());
                        bool ok = dw == wkid && def.GetShapeType() == s.Type && def.GetFields().Any(f => f.Name == "Include");
                        if (ok) continue;
                        Log.Write($"SYNC recreate {s.Fc}: layer wkid {dw} vs {wkid}, shape {def.GetShapeType()} vs {s.Type}");
                        del.Delete(new FeatureClassDescription(def));
                        anyDelete = true;
                    }
                    if (anyDelete && !del.Build()) throw new InvalidOperationException("Could not replace the NoiseBox input feature classes: " + string.Join("; ", del.ErrorMessages));
                }
                // 2. create what is missing
                using (var gdb = new Geodatabase(conn))
                {
                    var existing = gdb.GetDefinitions<FeatureClassDefinition>().Select(d => d.GetName()).ToHashSet();
                    var sb = new SchemaBuilder(gdb);
                    bool changed = false;
                    foreach (var s in specs)
                    {
                        if (existing.Contains(s.Fc) || !any) continue;
                        sb.Create(new FeatureClassDescription(s.Fc, FieldsFor(s.Type), new ShapeDescription(s.Type, sr)));
                        changed = true;
                    }
                    if (changed)
                    {
                        bool built = sb.Build();
                        Log.Write("INPUT LAYERS schema build " + (built ? "ok" : "FAILED: " + string.Join("; ", sb.ErrorMessages)));
                        if (!built) throw new InvalidOperationException("Could not create the NoiseBox input feature classes: " + string.Join("; ", sb.ErrorMessages));
                    }
                }
            }
            catch (InvalidOperationException) when (retry)
            {
                // the geodatabase is only derived data (rebuilt from the scenario): replace a damaged one and try once more
                foreach (var old in map.GetLayersAsFlattenedList().OfType<GroupLayer>().Where(g => g.Name == GroupName).ToList()) map.RemoveLayer(old);
                GC.Collect(); GC.WaitForPendingFinalizers();
                try { Directory.Delete(gdbPath, true); }
                catch { _gdbName = "NoiseBox_inputs_" + DateTime.Now.ToString("yyyyMMddHHmmss") + ".gdb"; }
                Log.Write("SYNC repair: geodatabase replaced (" + _gdbName + ")");
                return SyncCore(doc, preview, false);
            }

            using (var gdb = new Geodatabase(conn))
            {
                foreach (var s in specs)
                {
                    FeatureClass fc;
                    try { fc = gdb.OpenDataset<FeatureClass>(s.Fc); } catch (Exception ex) { if (s.Rows.Count > 0) Log.Write("INPUT LAYERS cannot open " + s.Fc + ": " + ex.Message); continue; }
                    using (fc)
                    {
                        var def = fc.GetDefinition();
                        string shapeField = def.GetShapeField();
                        gdb.ApplyEdits(() =>
                        {
                            fc.DeleteRows(new QueryFilter());
                            foreach (var r in s.Rows)
                            {
                                var g = r.Shape;
                                if (g.SpatialReference != null && ProApi.Wkid(g.SpatialReference) != wkid) g = GeometryEngine.Instance.Project(g, sr);
                                if (g is Polygon) g = GeometryEngine.Instance.SimplifyAsFeature(g, true);        // clockwise exterior rings, valid feature
                                using var rb = fc.CreateRowBuffer();
                                foreach (var kv in r.Attr) { try { rb[kv.Key] = kv.Value; } catch { } }
                                rb[shapeField] = g;
                                fc.CreateRow(rb).Dispose();
                            }
                        });
                    }
                }
            }

            // layers in Contents
            var group = map.GetLayersAsFlattenedList().OfType<GroupLayer>().FirstOrDefault(g => g.Name == GroupName);
            foreach (var s in specs)
            {
                if (s.Rows.Count == 0) continue;
                var found = map.GetLayersAsFlattenedList().OfType<FeatureLayer>().FirstOrDefault(l => l.Name == s.Label && l.Parent is GroupLayer gl && gl.Name == GroupName);
                if (found != null) continue;
                group ??= LayerFactory.Instance.CreateGroupLayer(map, 0, GroupName);
                var uri = new Uri(Path.Combine(gdbPath, s.Fc));
                var lp = new FeatureLayerCreationParams(uri)
                {
                    Name = s.Label,
                    RendererDefinition = new SimpleRendererDefinition { SymbolTemplate = s.Symbol() },
                };
                LayerFactory.Instance.CreateLayer<FeatureLayer>(lp, group);
            }
            foreach (var fl in map.GetLayersAsFlattenedList().OfType<FeatureLayer>().Where(l => l.Parent is GroupLayer gl && gl.Name == GroupName))
                fl.ClearDisplayCache();
            mv.Redraw(true);
            LastError = null;
            Log.Write("SYNC done");
            return true;
        }

        private static List<DdlField> FieldsFor(GeometryType t)
        {
            var f = new List<DdlField>
            {
                new DdlField("Name", FieldType.String) { Length = 120 },
                new DdlField("Kind", FieldType.String) { Length = 24 },
                new DdlField("SID", FieldType.String) { Length = 24 },
                new DdlField("Height_m", FieldType.Double),
                new DdlField("Include", FieldType.Integer),
                new DdlField("Note", FieldType.String) { Length = 200 },
            };
            return f;
        }

        private static List<Spec> BuildSpecs(ScenarioDoc doc, JsonObject preview, SpatialReference analysisSr, int wkid)
        {
            var src = new Spec { Fc = "NB_Source", Label = "NoiseBox source", Type = GeometryType.Point,
                Symbol = () => SymbolFactory.Instance.ConstructPointSymbol(C(200, 30, 30), 13, SimpleMarkerStyle.Circle).MakeSymbolReference() };
            var bar = new Spec { Fc = "NB_Barriers", Label = "NoiseBox noise barriers", Type = GeometryType.Polyline,
                Symbol = () => SymbolFactory.Instance.ConstructLineSymbol(C(40, 40, 40), 4, SimpleLineStyle.Solid).MakeSymbolReference() };
            var bld = new Spec { Fc = "NB_Buildings", Label = "NoiseBox buildings", Type = GeometryType.Polygon,
                Symbol = () => SymbolFactory.Instance.ConstructPolygonSymbol(C(150, 150, 150, 140), SimpleFillStyle.Solid,
                    SymbolFactory.Instance.ConstructStroke(C(70, 70, 70), 1.5)).MakeSymbolReference() };
            var enc = new Spec { Fc = "NB_Enclosures", Label = "NoiseBox enclosures", Type = GeometryType.Polygon,
                Symbol = () => SymbolFactory.Instance.ConstructPolygonSymbol(C(230, 140, 40, 120), SimpleFillStyle.Solid,
                    SymbolFactory.Instance.ConstructStroke(C(180, 100, 20), 2)).MakeSymbolReference() };
            var area = new Spec { Fc = "NB_Area", Label = "NoiseBox receiver area", Type = GeometryType.Polygon,
                Symbol = () => SymbolFactory.Instance.ConstructPolygonSymbol(C(0, 112, 192, 15), SimpleFillStyle.Solid,
                    SymbolFactory.Instance.ConstructStroke(C(0, 112, 192), 2, SimpleLineStyle.Dash)).MakeSymbolReference() };

            // source
            double? sx = doc.GetDouble("source.x"), sy = doc.GetDouble("source.y");
            int sw = (int?)doc.Root["source"]?["input_wkid"] ?? wkid;
            if (preview?["source"]?["x"] != null) { sx = (double)preview["source"]["x"]; sy = (double)preview["source"]["y"]; sw = wkid; }
            if (sx.HasValue && sy.HasValue && sw != 0)
            {
                var r = new Row { Shape = MapPointBuilderEx.CreateMapPoint(sx.Value, sy.Value, SpatialReferenceBuilder.CreateSpatialReference(sw)) };
                r.Attr["Name"] = doc.GetString("source.name") ?? "Source";
                r.Attr["Kind"] = "source";
                r.Attr["SID"] = "source";
                if (doc.GetDouble("source.height_m") is double h) r.Attr["Height_m"] = h;
                r.Attr["Include"] = 1;
                src.Rows.Add(r);
            }

            // structures
            foreach (var st in doc.Structures.OfType<JsonObject>())
            {
                if (!((bool?)st["visible"] ?? true)) continue;                       // not drawn on the map = not in the layer
                int w = (int?)st["input_wkid"] ?? wkid;
                if (w == 0) continue;
                var ssr = SpatialReferenceBuilder.CreateSpatialReference(w);
                string type = (string)st["type"];
                var row = new Row();
                row.Attr["Name"] = (string)st["name"];
                row.Attr["Kind"] = type;
                row.Attr["SID"] = (string)st["id"];
                row.Attr["Include"] = ((bool?)st["include"] ?? true) ? 1 : 0;
                if (type == "barrier")
                {
                    var path = (st["path"] as JsonArray) ?? OverlayManager.PreciseBarrierPath(st);
                    if (path == null || path.Count < 2) continue;
                    row.Shape = PolylineBuilderEx.CreatePolyline(Coords(path), ssr);
                    var vm = (string)st["vertical"]?["mode"];
                    if (vm == "relative" && st["vertical"]?["value"] != null) row.Attr["Height_m"] = (double)st["vertical"]["value"];
                    row.Attr["Note"] = vm == "absolute" ? "top elevation " + (string)st["vertical"]?["value"]?.ToString() + " m" : "height above local terrain";
                    bar.Rows.Add(row);
                }
                else
                {
                    var ring = st["footprint"] as JsonArray;
                    if (ring == null && type == "enclosure") ring = OverlayManager.EnclosureRing(doc, st, preview);
                    if (ring == null || ring.Count < 3) continue;
                    row.Shape = PolygonBuilderEx.CreatePolygon(Coords(ring), ssr);
                    if (st["height_m"] != null) row.Attr["Height_m"] = (double)st["height_m"];
                    (type == "building" ? bld : enc).Rows.Add(row);
                }
            }

            // receiver area (analysis system, as resolved by the preview; without a preview: the stored rings or extent)
            var rings = new List<JsonArray>();
            int aw = wkid;
            if (preview?["area"]?["rings"] is JsonArray pr) rings.AddRange(pr.OfType<JsonArray>());
            else if (doc.GetString("area.mode") == "polygon" && doc.Get("area.rings") is JsonArray dr) { rings.AddRange(dr.OfType<JsonArray>()); aw = (int?)doc.Root["area"]?["input_wkid"] ?? wkid; }
            else if (doc.GetString("area.mode") == "extent" && doc.Get("area.extent") is JsonArray e && e.Count == 4)
            {
                double x0 = (double)e[0], y0 = (double)e[1], x1 = (double)e[2], y1 = (double)e[3];
                rings.Add(new JsonArray(new JsonArray(x0, y0), new JsonArray(x1, y0), new JsonArray(x1, y1), new JsonArray(x0, y1)));
                aw = (int?)doc.Root["area"]?["input_wkid"] ?? wkid;
            }
            if (aw != 0)
            {
                var asr = SpatialReferenceBuilder.CreateSpatialReference(aw);
                int k = 0;
                foreach (var ring in rings)
                {
                    if (ring.Count < 3) continue;
                    var r = new Row { Shape = PolygonBuilderEx.CreatePolygon(Coords(ring), asr) };
                    r.Attr["Name"] = "Receiver area" + (rings.Count > 1 ? " " + (++k) : "");
                    r.Attr["Kind"] = "area";
                    r.Attr["SID"] = "area";
                    r.Attr["Include"] = 1;
                    r.Attr["Note"] = doc.GetString("area.mode");
                    area.Rows.Add(r);
                }
            }
            return new List<Spec> { area, bld, enc, bar, src };                      // listed bottom to top; each new layer goes on top
        }

        private static List<Coordinate2D> Coords(JsonNode ring) => ring.AsArray().Select(p => new Coordinate2D((double)p[0], (double)p[1])).ToList();
    }
}
