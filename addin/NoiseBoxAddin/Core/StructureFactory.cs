using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;

namespace NoiseBoxAddin.Core
{
    /// <summary>Builds scenario objects with the same keys the Python side reads (noisebox/scenario.py, tests/scn_common.py).</summary>
    internal static class StructureFactory
    {
        public static JsonArray Ring(IEnumerable<double[]> pts) => new JsonArray(pts.Select(p => (JsonNode)new JsonArray(p[0], p[1])).ToArray());

        private static JsonObject Common(string type, string name) => new JsonObject
        {
            ["id"] = ScenarioDoc.NewId(), ["type"] = type, ["name"] = name, ["include"] = true, ["visible"] = true,
        };

        public static JsonObject Building(string name, IEnumerable<double[]> footprint, int wkid, double? height, JsonNode layer = null)
        {
            var b = Common("building", name);
            b["footprint"] = Ring(footprint);
            b["input_wkid"] = wkid;
            b["height_m"] = height;
            b["height_source"] = new JsonObject { ["mode"] = "single" };
            b["layer"] = layer;
            return b;
        }

        public static JsonObject Barrier(string name, IEnumerable<double[]> path, int wkid, double? height, JsonNode layer = null)
        {
            var b = Common("barrier", name);
            b["path"] = path == null ? null : Ring(path);
            b["input_wkid"] = wkid;
            b["placement"] = new JsonObject { ["mode"] = path == null ? "straight" : "drawn" };
            b["vertical"] = new JsonObject { ["mode"] = "relative", ["value"] = height };   // or "absolute" (top elevation)
            b["gap_m"] = 0.0;
            b["transmission"] = new JsonObject { ["enabled"] = false, ["material"] = null };
            b["layer"] = layer;
            return b;
        }

        public static JsonObject PreciseBarrier(string name, double sx, double sy, int wkid, double length, double azimuth, double height)
        {
            var b = Barrier(name, null, wkid, height);
            b["placement"] = new JsonObject
            {
                ["mode"] = "straight", ["start"] = new JsonArray(sx, sy), ["length_m"] = length, ["azimuth_deg"] = azimuth,
            };
            return b;
        }

        public static JsonObject EmptyMaterial(string mode = "mass_law") => new JsonObject
        {
            ["mode"] = mode, ["surface_mass_kg_m2"] = null, ["thickness_m"] = null, ["volume_density_kg_m3"] = null,
            ["solid"] = true, ["tl_model"] = "normal",
            ["TL"] = new JsonArray(Enumerable.Repeat<JsonNode>(null, 8).ToArray()),
            ["alpha"] = new JsonArray(Enumerable.Repeat<JsonNode>(null, 8).ToArray()),
        };

        public static JsonObject RectangleEnclosure(string name, double? length, double? width, double? height)
        {
            var e = Common("enclosure", name);
            e["source_link"] = "source";
            e["mode"] = "rectangle";
            e["rect"] = new JsonObject { ["length_m"] = length, ["width_m"] = width, ["orientation_deg"] = 0.0, ["offset"] = new JsonArray(0.0, 0.0) };
            e["footprint"] = null;
            e["input_wkid"] = null;
            e["height_m"] = height;
            e["open_area_m2"] = 0.0;
            e["faces"] = new JsonObject { ["mode"] = "single", ["all"] = EmptyMaterial(), ["faces"] = new JsonObject() };
            return e;
        }

        public static JsonObject PolygonEnclosure(string name, IEnumerable<double[]> footprint, int wkid, double? height)
        {
            var e = RectangleEnclosure(name, 1, 1, height);
            e["mode"] = "polygon";
            e["footprint"] = Ring(footprint);
            e["input_wkid"] = wkid;
            return e;
        }
    }
}
