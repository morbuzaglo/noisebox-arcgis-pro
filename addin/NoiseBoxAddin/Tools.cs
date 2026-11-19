using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using System.Windows.Input;
using ArcGIS.Core.CIM;
using ArcGIS.Core.Data;
using ArcGIS.Core.Geometry;
using ArcGIS.Desktop.Framework.Threading.Tasks;
using ArcGIS.Desktop.Mapping;
using NoiseBoxAddin.Buttons;
using NoiseBoxAddin.Core;

namespace NoiseBoxAddin.Tools
{
    /// <summary>Base for the sketch tools. Esc cancels an unfinished sketch (framework behaviour) and says so in the pane.
    /// Snapping follows the Pro snapping settings.</summary>
    internal abstract class SketchToolBase : MapTool
    {
        protected abstract string Section { get; }

        protected SketchToolBase(SketchGeometryType type)
        {
            IsSketchTool = true;
            SketchType = type;
            SketchOutputMode = SketchOutputMode.Map;
            UseSnapping = true;
        }

        protected override Task OnToolActivateAsync(bool hasMapViewChanged)
        {
            Ui.Run(() => NoiseBoxPaneViewModel_Show());
            return Task.CompletedTask;
        }

        private void NoiseBoxPaneViewModel_Show() => UI.NoiseBoxPaneViewModel.Show(Section);

        /// <summary>Esc cancels an unfinished sketch (done by the framework); this only says so in the pane.</summary>
        protected override void OnToolKeyDown(MapViewKeyEventArgs k)
        {
            if (k.Key == Key.Escape) Ui.Run(() => { if (Ui.Pane != null) Ui.Pane.Status = "Cancelled."; });
            base.OnToolKeyDown(k);
        }

        protected static int Wkid(Geometry g) => ProApi.Wkid(g.SpatialReference);
    }

    // ---------------------------------------------------------------- source
    internal class PlaceSourceTool : SketchToolBase
    {
        public PlaceSourceTool() : base(SketchGeometryType.Point) { }
        protected override string Section => "source";

        protected override Task<bool> OnSketchCompleteAsync(Geometry geometry)
        {
            if (geometry is MapPoint p) Ui.Run(() => Ui.Pane?.SetSourceFromMap(p.X, p.Y, Wkid(p)));
            return Task.FromResult(true);
        }
    }

    /// <summary>Move Source: click the new position; the old one is replaced and its coordinates are shown immediately.</summary>
    internal class MoveSourceTool : PlaceSourceTool { }

    internal class PickSourceTool : SketchToolBase
    {
        public PickSourceTool() : base(SketchGeometryType.Point) { }
        protected override string Section => "source";

        protected override async Task<bool> OnSketchCompleteAsync(Geometry geometry)
        {
            var mv = MapView.Active;
            if (mv == null || geometry is not MapPoint p) return false;
            double tol = mv.Extent.Width / 80.0;
            var hit = GeometryEngine.Instance.Buffer(p, tol);
            var sel = mv.GetFeatures(hit);
            foreach (var kv in sel.ToDictionary<FeatureLayer>())
            {
                if (kv.Key.ShapeType != esriGeometryType.esriGeometryPoint || kv.Value.Count == 0) continue;
                var found = await ProApi.FindPointsAsync(kv.Key, kv.Value[0].ToString());
                if (found.Count > 0)
                {
                    var c = found[0];
                    Ui.Run(() => Ui.Pane.SelectedPointLayer = Ui.Pane.PointLayers.FirstOrDefault(l => l.Layer == kv.Key));
                    Ui.Run(() => Ui.Pane.Doc.SetSourceLocation("layer", c.X, c.Y, c.Wkid, ProApi.LayerRef(kv.Key, c.Oid)));
                    Ui.Run(() => Ui.Pane.ShowSourceCoordinates());
                    return true;
                }
            }
            Ui.Run(() => Ui.Pane.Status = "No point feature under the click (SRC-006).");
            return true;
        }
    }

    /// <summary>Heading: click the direction. 0 deg = map north (up), clockwise; measured from the source.</summary>
    internal class HeadingTool : SketchToolBase
    {
        public HeadingTool() : base(SketchGeometryType.Point) { }
        protected override string Section => "source";

        protected override Task<bool> OnSketchCompleteAsync(Geometry geometry)
        {
            var pv = NoiseBoxModule.Current.LastPreview;
            if (geometry is MapPoint p && pv?["source"] != null)
            {
                int w = (int)pv["source"]["wkid"];
                var q = (MapPoint)GeometryEngine.Instance.Project(p, SpatialReferenceBuilder.CreateSpatialReference(w));
                double dx = q.X - (double)pv["source"]["x"], dy = q.Y - (double)pv["source"]["y"];
                Ui.Run(() => Ui.Pane?.SetHeading(Math.Atan2(dx, dy) * 180.0 / Math.PI));
            }
            return Task.FromResult(true);
        }
    }

    // ---------------------------------------------------------------- area
    internal class AreaPolygonTool : SketchToolBase
    {
        public AreaPolygonTool() : base(SketchGeometryType.Polygon) { }
        protected override string Section => "terrain";

        protected override Task<bool> OnSketchCompleteAsync(Geometry geometry)
        {
            if (geometry is Polygon poly) { var ring = ProApi.Points(poly); int w = Wkid(poly); Ui.Run(() => Ui.Pane?.SetAreaPolygon(ring, w)); }
            return Task.FromResult(true);
        }
    }

    internal class AreaRectangleTool : AreaPolygonTool
    {
        public AreaRectangleTool() { SketchType = SketchGeometryType.Rectangle; }
    }

    // ---------------------------------------------------------------- structures
    internal class BuildingTool : SketchToolBase
    {
        public BuildingTool() : base(SketchGeometryType.Polygon) { }
        protected override string Section => "structures";

        protected override Task<bool> OnSketchCompleteAsync(Geometry geometry)
        {
            if (geometry is Polygon poly)
            {
                var ring = ProApi.Points(poly); int w = Wkid(poly);
                Ui.Run(() => Ui.Pane?.AddStructure(StructureFactory.Building("Building", ring, w, null)));      // height is entered in the pane
            }
            return Task.FromResult(true);
        }
    }

    internal class BarrierTool : SketchToolBase
    {
        public BarrierTool() : base(SketchGeometryType.Line) { }
        protected override string Section => "structures";

        protected override Task<bool> OnSketchCompleteAsync(Geometry geometry)
        {
            if (geometry is Polyline line)
            {
                var path = ProApi.Points(line); int w = Wkid(line);
                Ui.Run(() => Ui.Pane?.AddStructure(StructureFactory.Barrier("Barrier", path, w, null)));
            }
            return Task.FromResult(true);
        }
    }

    /// <summary>Precise placement, step 1: click the start point; length, azimuth and height are then typed in the pane and the
    /// barrier on the map follows every edit.</summary>
    internal class BarrierStartTool : SketchToolBase
    {
        public BarrierStartTool() : base(SketchGeometryType.Point) { }
        protected override string Section => "structures";

        protected override Task<bool> OnSketchCompleteAsync(Geometry geometry)
        {
            if (geometry is MapPoint p)
                Ui.Run(() =>
                {
                    var b = StructureFactory.PreciseBarrier("Barrier", p.X, p.Y, Wkid(p), 50.0, 0.0, 3.0);
                    Ui.Pane?.AddStructure(b);
                    UI.NoiseBoxPaneViewModel.Show("structures", "sname");
                });
            return Task.FromResult(true);
        }
    }

    internal class EnclosureTool : SketchToolBase
    {
        public EnclosureTool() : base(SketchGeometryType.Polygon) { }
        protected override string Section => "structures";

        protected override Task<bool> OnSketchCompleteAsync(Geometry geometry)
        {
            if (geometry is Polygon poly)
            {
                var ring = ProApi.Points(poly); int w = Wkid(poly);
                Ui.Run(() => Ui.Pane?.AddStructure(StructureFactory.PolygonEnclosure("Enclosure", ring, w, null)));
            }
            return Task.FromResult(true);
        }
    }

    /// <summary>Select Structure: click a drawn structure; its properties open in the pane. Hit-testing uses the geometry of the
    /// last preview (structures are scenario objects, not map layers).</summary>
    internal class PickStructureTool : SketchToolBase
    {
        public PickStructureTool() : base(SketchGeometryType.Point) { }
        protected override string Section => "structures";

        protected override Task<bool> OnSketchCompleteAsync(Geometry geometry)
        {
            var pv = NoiseBoxModule.Current.LastPreview;
            if (geometry is not MapPoint p || pv?["structures"] is not JsonArray list || pv["source"] == null) return Task.FromResult(false);
            var q = (MapPoint)GeometryEngine.Instance.Project(p, SpatialReferenceBuilder.CreateSpatialReference((int)pv["source"]["wkid"]));
            double tol = (MapView.Active?.Extent.Width ?? 100) / 100.0;
            string hit = null;
            foreach (var s in list.OfType<JsonObject>())
            {
                if (!((bool?)s["visible"] ?? true)) continue;                         // hidden objects are not drawn, so they cannot be clicked
                if (s["ring"] is JsonArray ring && InRing(q.X, q.Y, ring)) { hit = (string)s["id"]; break; }
                if (s["path"] is JsonArray path && NearPath(q.X, q.Y, path, tol)) { hit = (string)s["id"]; break; }
            }
            if (hit != null) Ui.Run(() => Ui.Pane?.SelectStructure(hit));
            return Task.FromResult(true);
        }

        private static bool InRing(double x, double y, JsonArray r)
        {
            bool inside = false;
            for (int i = 0, j = r.Count - 1; i < r.Count; j = i++)
            {
                double xi = (double)r[i][0], yi = (double)r[i][1], xj = (double)r[j][0], yj = (double)r[j][1];
                if ((yi > y) != (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
            }
            return inside;
        }

        private static bool NearPath(double x, double y, JsonArray p, double tol)
        {
            for (int i = 0; i + 1 < p.Count; i++)
            {
                double ax = (double)p[i][0], ay = (double)p[i][1], bx = (double)p[i + 1][0], by = (double)p[i + 1][1];
                double dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy;
                double t = l2 < 1e-12 ? 0 : Math.Max(0, Math.Min(1, ((x - ax) * dx + (y - ay) * dy) / l2));
                if (Math.Sqrt(Math.Pow(x - (ax + t * dx), 2) + Math.Pow(y - (ay + t * dy), 2)) <= tol) return true;
            }
            return false;
        }
    }
}
