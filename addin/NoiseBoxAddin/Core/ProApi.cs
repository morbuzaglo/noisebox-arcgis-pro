using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using ArcGIS.Core.CIM;
using ArcGIS.Core.Data;
using ArcGIS.Core.Geometry;
using ArcGIS.Desktop.Core.Geoprocessing;
using ArcGIS.Desktop.Framework;
using ArcGIS.Desktop.Framework.Threading.Tasks;
using ArcGIS.Desktop.Mapping;

namespace NoiseBoxAddin.Core
{
    internal sealed class LayerItem
    {
        public Layer Layer { get; set; }
        public string Name => Layer.Name;
        public override string ToString() => Layer.Name;
    }

    internal sealed class PointCandidate
    {
        public long Oid { get; set; }
        public string Label { get; set; }
        public double X { get; set; }
        public double Y { get; set; }
        public int Wkid { get; set; }
        public override string ToString() => Label;
    }

    /// <summary>Everything that touches the Pro SDK (layers, selections, geometry, overlay, geoprocessing).</summary>
    internal static class ProApi
    {
        public static int Wkid(SpatialReference sr) => sr == null ? 0 : (sr.Wkid != 0 ? sr.Wkid : sr.LatestWkid);

        // ---------------------------------------------------------------- layers (drop-down lists)
        public static Task<List<LayerItem>> LayersAsync(esriGeometryType shape) => QueuedTask.Run(() =>
            MapView.Active?.Map?.GetLayersAsFlattenedList().OfType<FeatureLayer>().Where(l => l.ShapeType == shape)
                .Select(l => new LayerItem { Layer = l }).ToList() ?? new List<LayerItem>());

        public static Task<List<LayerItem>> RasterLayersAsync() => QueuedTask.Run(() =>
            MapView.Active?.Map?.GetLayersAsFlattenedList().OfType<RasterLayer>()
                .Select(l => new LayerItem { Layer = l }).ToList() ?? new List<LayerItem>());

        public static string DataPath(Layer layer) => layer.GetPath()?.LocalPath;

        // ---------------------------------------------------------------- the map's ground (elevation surface)
        internal sealed class GroundItem
        {
            public string Name { get; set; }
            public string Path { get; set; }               // local raster file or geodatabase raster; null for web services
            public string Source { get; set; }             // as Pro reports it (shown in messages)
            public bool IsLocal => !string.IsNullOrEmpty(Path) && (File.Exists(Path) || Directory.Exists(Path) || Path.Contains(".gdb"));
        }

        /// <summary>The sources of the active map's ground elevation surface (Contents > Elevation Surfaces > Ground),
        /// top priority first. A source that is a web service has no local file and cannot be used directly.</summary>
        public static Task<List<GroundItem>> GroundSourcesAsync() => QueuedTask.Run(() =>
        {
            var list = new List<GroundItem>();
            var map = MapView.Active?.Map;
            if (map == null) return list;
            var surface = map.GetGroundElevationSurfaceLayer();
            if (surface == null) return list;
            foreach (var l in surface.Layers)
            {
                string p = null, src = null;
                try { var u = l.GetPath(); src = u?.ToString(); p = u != null && u.IsFile ? u.LocalPath : null; } catch { }
                list.Add(new GroundItem { Name = l.Name, Path = p, Source = src });
            }
            return list;
        });

        // ---------------------------------------------------------------- source from a point layer
        /// <summary>Selected points of a layer (one entry per point). If several are selected the pane lets the user choose.</summary>
        public static Task<List<PointCandidate>> SelectedPointsAsync(FeatureLayer layer) => QueuedTask.Run(() =>
        {
            var oids = layer.GetSelection().GetObjectIDs();
            return oids.Count == 0 ? new List<PointCandidate>() : ReadPoints(layer, new QueryFilter { ObjectIDs = oids });
        });

        /// <summary>Find a point by feature name (the layer's display field) or by object ID.</summary>
        public static Task<List<PointCandidate>> FindPointsAsync(FeatureLayer layer, string text) => QueuedTask.Run(() =>
        {
            string oidField = layer.GetFeatureClass().GetDefinition().GetObjectIDField();
            string disp = DisplayFieldOf(layer);
            string t = text.Replace("'", "''");
            var where = long.TryParse(text, out var id) ? $"{oidField} = {id} OR {disp} = '{t}'" : $"{disp} = '{t}'";
            try { return ReadPoints(layer, new QueryFilter { WhereClause = where }); }
            catch { return long.TryParse(text, out var id2) ? ReadPoints(layer, new QueryFilter { WhereClause = $"{oidField} = {id2}" }) : new List<PointCandidate>(); }
        });

        private static string DisplayFieldOf(FeatureLayer layer) =>
            (layer.GetDefinition() as CIMFeatureLayer)?.FeatureTable?.DisplayField
            ?? layer.GetFeatureClass().GetDefinition().GetObjectIDField();

        private static List<PointCandidate> ReadPoints(FeatureLayer layer, QueryFilter filter)
        {
            var list = new List<PointCandidate>();
            string disp = DisplayFieldOf(layer);
            using var cur = layer.Search(filter);
            while (cur.MoveNext())
            {
                using var f = cur.Current as Feature;
                if (f?.GetShape() is not MapPoint p || p.IsEmpty) continue;
                object name = null;
                try { name = f[disp]; } catch { }
                list.Add(new PointCandidate
                {
                    Oid = f.GetObjectID(), X = p.X, Y = p.Y, Wkid = Wkid(p.SpatialReference),
                    Label = $"{name} (ID {f.GetObjectID()})",
                });
            }
            return list.OrderBy(c => c.Oid).ToList();
        }

        public static JsonObject LayerRef(FeatureLayer layer, long oid) => new JsonObject
        {
            ["path"] = DataPath(layer), ["name"] = layer.Name, ["oid"] = oid,
        };

        // ---------------------------------------------------------------- geometry out of layers and sketches
        public static List<double[]> Points(Polygon poly, int part = 0) => PartPoints(poly.Parts[part]);

        public static List<double[]> Points(Polyline line, int part = 0) => PartPoints(line.Parts[part], true);

        private static List<double[]> PartPoints(ReadOnlySegmentCollection segs, bool endPoint = false)
        {
            var pts = segs.Select(s => new[] { s.StartPoint.X, s.StartPoint.Y }).ToList();
            if (endPoint && segs.Count > 0) pts.Add(new[] { segs.Last().EndPoint.X, segs.Last().EndPoint.Y });
            return pts;
        }

        /// <summary>Polygons of a layer: the selected ones, or the entire layer. One ring (exterior) per part.</summary>
        public static Task<(List<List<double[]>> rings, int wkid)> PolygonRingsAsync(FeatureLayer layer, bool selectedOnly) => QueuedTask.Run(() =>
        {
            var rings = new List<List<double[]>>();
            int wkid = Wkid(layer.GetSpatialReference());
            var filter = new QueryFilter();
            if (selectedOnly) filter.ObjectIDs = layer.GetSelection().GetObjectIDs();
            using var cur = layer.Search(filter);
            while (cur.MoveNext())
            {
                using var f = cur.Current as Feature;
                if (f?.GetShape() is Polygon pg)
                    for (int i = 0; i < pg.PartCount; i++) rings.Add(Points(pg, i));
            }
            return (rings, wkid);
        });

        public static Task<long> SelectedCountAsync(FeatureLayer layer) => QueuedTask.Run(() => layer.GetSelection().GetCount());

        // ---------------------------------------------------------------- map extent
        public static Task<(double xmin, double ymin, double xmax, double ymax, int wkid)?> MapExtentAsync() => QueuedTask.Run(() =>
        {
            var e = MapView.Active?.Extent;
            if (e == null) return ((double, double, double, double, int)?)null;
            return (e.XMin, e.YMin, e.XMax, e.YMax, Wkid(e.SpatialReference));
        });

        public static Task<SpatialReference> MapSrAsync() => QueuedTask.Run(() => MapView.Active?.Map?.SpatialReference);

        // ---------------------------------------------------------------- coordinate system helpers
        public static Task<(bool geographic, string name)> CrsInfoAsync(int wkid) => QueuedTask.Run(() =>
        {
            var sr = SpatialReferenceBuilder.CreateSpatialReference(wkid);
            return (sr.IsGeographic, sr.Name);
        });

        // ---------------------------------------------------------------- zoom
        public static Task ZoomToAsync(Geometry g) => QueuedTask.Run(() => MapView.Active?.ZoomToAsync(g, TimeSpan.FromSeconds(0.4)));

        // ---------------------------------------------------------------- run (geoprocessing tool in Pro's own Python)
        /// <summary>Runs NoiseBox.pyt\RunScenario in-process, so the results are added to the open map by Pro's Python.</summary>
        public static async Task<(bool ok, List<string> messages)> RunAsync(ScenarioDoc doc, CancelableProgressorSource cps, Action<string> onMessage)
        {
            var file = Path.Combine(Path.GetTempPath(), "noisebox_run_" + (string)doc.Root["id"] + ".nbscenario.json");
            File.WriteAllText(file, doc.Root.ToJsonString());
            var tool = Path.Combine(PythonBridge.ToolboxPath(), "RunScenario");
            var msgs = new List<string>();
            var result = await Geoprocessing.ExecuteToolAsync(tool, Geoprocessing.MakeValueArray(file), null, cps.Progressor.CancellationToken,
                (name, o) => { });
            foreach (var m in result.Messages) { msgs.Add(m.Text); onMessage?.Invoke(m.Text); }
            if (!result.IsFailed && msgs.Any(m => m != null && m.Contains("NOISEBOX_MAP_ADD_FAILED")))
            {
                int n = await ResultLayers.AddAsync(doc.GetString("name") ?? "Scenario", ResultLayers.ParseRunName(msgs), ResultLayers.ParseCreated(msgs));
                string add = $"Added {n} result layer(s) to the map (the tool could not).";
                msgs.Add(add); onMessage?.Invoke(add);
            }
            try { await InputLayers.MoveToTopAsync(); } catch (Exception e) { Log.Write("MOVE inputs to top: " + e.Message); }
            return (!result.IsFailed, msgs);
        }
    }

    /// <summary>The scenario drawn on the map as overlay graphics (never as editable GIS features).</summary>
    internal sealed class OverlayManager
    {
        private readonly List<IDisposable> _items = new List<IDisposable>();

        public void Clear()
        {
            foreach (var d in _items) d.Dispose();
            _items.Clear();
        }

        private static CIMColor C(int r, int g, int b, int a = 255) => ColorFactory.Instance.CreateRGBColor(r, g, b, a);

        private void Add(Geometry g, CIMSymbol sym)
        {
            var mv = MapView.Active;
            if (mv == null || g == null) return;
            var pg = g.SpatialReference != null && mv.Map.SpatialReference != null && ProApi.Wkid(g.SpatialReference) != ProApi.Wkid(mv.Map.SpatialReference)
                ? GeometryEngine.Instance.Project(g, mv.Map.SpatialReference) : g;
            _items.Add(mv.AddOverlay(pg, sym.MakeSymbolReference()));
        }

        private static List<Coordinate2D> Coords(JsonNode ring) =>
            ring.AsArray().Select(p => new Coordinate2D((double)p[0], (double)p[1])).ToList();

        /// <summary>Draws source, heading arrow, receiver area, DTM gaps and the structures that are visible. Participation
        /// (included in the run) only changes how they are drawn; hiding one never changes the calculation.</summary>
        public Task DrawAsync(ScenarioDoc doc, JsonObject preview, string selectedId, string selectedFace = null, bool layersCarryObjects = false) => QueuedTask.Run(() =>
        {
            Clear();
            var mv = MapView.Active;
            if (mv == null) return;
            double width = mv.Extent.Width;

            // receiver area
            var area = preview?["area"]?["rings"] as JsonArray;
            int wkid = (int?)preview?["source"]?["wkid"] ?? 0;
            if (!layersCarryObjects && area != null && wkid != 0)
            {
                var sr = SpatialReferenceBuilder.CreateSpatialReference(wkid);
                var outline = SymbolFactory.Instance.ConstructStroke(C(0, 112, 192), 2, SimpleLineStyle.Dash);
                var fill = SymbolFactory.Instance.ConstructPolygonSymbol(C(0, 112, 192, 20), SimpleFillStyle.Solid, outline);
                foreach (var ring in area) Add(PolygonBuilderEx.CreatePolygon(Coords(ring), sr), fill);
            }

            // gaps in DTM coverage
            var gaps = preview?["coverage"]?["gaps"] as JsonArray;
            if (gaps != null && wkid != 0)
            {
                var sr = SpatialReferenceBuilder.CreateSpatialReference(wkid);
                var sym = SymbolFactory.Instance.ConstructPointSymbol(C(220, 0, 0), 6, SimpleMarkerStyle.Square);
                foreach (var g in gaps) Add(MapPointBuilderEx.CreateMapPoint((double)g[0], (double)g[1], sr), sym);
            }

            // structures
            foreach (var st in doc.Structures.OfType<JsonObject>())
            {
                if (!((bool?)st["visible"] ?? true)) continue;               // hidden drawing: not drawn, still calculated if included
                bool inc = (bool?)st["include"] ?? true;
                bool sel = (string)st["id"] == selectedId;
                if (layersCarryObjects && !sel) continue;       // objects are real layers in Contents; only the selected one is highlighted here
                int w = (int?)st["input_wkid"] ?? wkid;
                if (w == 0) continue;
                var sr = SpatialReferenceBuilder.CreateSpatialReference(w);
                var col = sel ? C(0, 200, 255) : inc ? C(90, 90, 90) : C(160, 160, 160);
                var style = inc ? SimpleLineStyle.Solid : SimpleLineStyle.Dash;
                var stroke = SymbolFactory.Instance.ConstructStroke(col, sel ? 3 : 1.5, style);
                string type = (string)st["type"];
                if (type == "barrier")
                {
                    var path = (st["path"] as JsonArray) ?? PreciseBarrierPath(st);
                    if (path != null && path.Count >= 2)
                        Add(PolylineBuilderEx.CreatePolyline(Coords(path), sr), SymbolFactory.Instance.ConstructLineSymbol(col, sel ? 5 : 3, style));
                }
                else
                {
                    var ring = st["footprint"] as JsonArray;
                    if (ring == null && type == "enclosure") ring = EnclosureRing(doc, st, preview);
                    if (ring != null && ring.Count >= 3)
                    {
                        var fillCol = type == "building" ? C(150, 150, 150, inc ? 120 : 40) : C(230, 140, 40, inc ? 110 : 40);
                        Add(PolygonBuilderEx.CreatePolygon(Coords(ring), sr), SymbolFactory.Instance.ConstructPolygonSymbol(fillCol, SimpleFillStyle.Solid, stroke));
                    }
                }
            }

            // the selected face of an enclosure (wall or roof), highlighted
            if (selectedId != null && selectedFace != null && wkid != 0)
            {
                var pst = (preview?["structures"] as JsonArray)?.FirstOrDefault(s => (string)s["id"] == selectedId);
                var face = (pst?["faces"] as JsonArray)?.FirstOrDefault(f => (string)f["name"] == selectedFace);
                var sr = SpatialReferenceBuilder.CreateSpatialReference(wkid);
                if (face?["p1"] != null)
                    Add(PolylineBuilderEx.CreatePolyline(new[] { new Coordinate2D((double)face["p1"][0], (double)face["p1"][1]),
                        new Coordinate2D((double)face["p2"][0], (double)face["p2"][1]) }, sr),
                        SymbolFactory.Instance.ConstructLineSymbol(C(255, 200, 0), 6, SimpleLineStyle.Solid));
                else if (face != null && pst?["ring"] is JsonArray rr)                      // the roof: outline the whole footprint
                    Add(PolygonBuilderEx.CreatePolygon(Coords(rr), sr), SymbolFactory.Instance.ConstructPolygonSymbol(C(255, 200, 0, 90), SimpleFillStyle.Solid,
                        SymbolFactory.Instance.ConstructStroke(C(255, 200, 0), 3, SimpleLineStyle.Solid)));
            }

            // source and heading arrow (0 deg = map north / grid +y, clockwise)
            var src = preview?["source"];
            if (src != null && wkid != 0)
            {
                var sr = SpatialReferenceBuilder.CreateSpatialReference(wkid);
                double x = (double)src["x"], y = (double)src["y"];
                if (!layersCarryObjects) Add(MapPointBuilderEx.CreateMapPoint(x, y, sr), SymbolFactory.Instance.ConstructPointSymbol(C(200, 30, 30), 12, SimpleMarkerStyle.Circle));
                bool directional = doc.GetString("source.directivity.mode") == "directional";
                if (directional)
                {
                    double az = (doc.GetDouble("source.directivity.heading_deg") ?? 0) * Math.PI / 180.0;
                    double L = width * 0.08;
                    double tx = x + L * Math.Sin(az), ty = y + L * Math.Cos(az);
                    var arrow = SymbolFactory.Instance.ConstructLineSymbol(C(200, 30, 30), 2.5, SimpleLineStyle.Solid);
                    Add(PolylineBuilderEx.CreatePolyline(new[] { new Coordinate2D(x, y), new Coordinate2D(tx, ty) }, sr), arrow);
                    double hl = L * 0.25;
                    var head = new[]
                    {
                        new Coordinate2D(tx, ty),
                        new Coordinate2D(tx - hl * Math.Sin(az - 0.45), ty - hl * Math.Cos(az - 0.45)),
                        new Coordinate2D(tx - hl * Math.Sin(az + 0.45), ty - hl * Math.Cos(az + 0.45)),
                    };
                    Add(PolygonBuilderEx.CreatePolygon(head, sr), SymbolFactory.Instance.ConstructPolygonSymbol(C(200, 30, 30), SimpleFillStyle.Solid));
                }
            }
        });

        internal static JsonArray PreciseBarrierPath(JsonObject st)
        {
            var pl = st["placement"];
            if ((string)pl?["mode"] != "straight" || pl["start"] == null || pl["length_m"] == null || pl["azimuth_deg"] == null) return null;
            double sx = (double)pl["start"][0], sy = (double)pl["start"][1], L = (double)pl["length_m"], a = (double)pl["azimuth_deg"] * Math.PI / 180.0;
            return new JsonArray(new JsonArray(sx, sy), new JsonArray(sx + L * Math.Sin(a), sy + L * Math.Cos(a)));
        }

        /// <summary>Footprint of a rectangle enclosure around the source (same rule as noisebox/structures.py rect_footprint).</summary>
        internal static JsonArray EnclosureRing(ScenarioDoc doc, JsonObject st, JsonObject preview)
        {
            var r = st["rect"]; var src = preview?["source"];
            if (r == null || src == null || r["length_m"] == null || r["width_m"] == null) return null;
            double L = (double)r["length_m"], W = (double)r["width_m"], az = ((double?)r["orientation_deg"] ?? 0) * Math.PI / 180.0;
            double ox = (double?)r["offset"]?[0] ?? 0, oy = (double?)r["offset"]?[1] ?? 0;
            double cx = (double)src["x"] + ox, cy = (double)src["y"] + oy;
            double ux = Math.Sin(az), uy = Math.Cos(az), vx = -uy, vy = ux, hl = L / 2, hw = W / 2;
            JsonNode P(double a, double b) => new JsonArray(cx + a * ux + b * vx, cy + a * uy + b * vy);
            return new JsonArray(P(-hl, -hw), P(hl, -hw), P(hl, hw), P(-hl, hw));
        }
    }
}
