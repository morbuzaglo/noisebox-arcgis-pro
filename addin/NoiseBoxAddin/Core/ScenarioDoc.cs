using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace NoiseBoxAddin.Core
{
    /// <summary>
    /// The scenario as JSON (schema "noisebox.scenario/1", defined in noisebox/scenario.py). The add-in edits the JSON
    /// directly, so a field added on the Python side is never lost. Paths look like "source.height_m" or
    /// "structures[2].vertical.value".
    /// </summary>
    internal sealed class ScenarioDoc
    {
        public const string Schema = "noisebox.scenario/1";
        public JsonObject Root { get; private set; }
        public string FilePath { get; set; }
        public bool Dirty { get; private set; }
        public event Action Changed;

        private ScenarioDoc(JsonObject root) { Root = root; EnsureDefaults(); }

        /// <summary>Fields added after a scenario file was written (per-band limits): fill them so older files open unchanged.</summary>
        public void EnsureDefaults()
        {
            if (Root["outputs"] is not JsonObject o) return;
            if (o["limit_bands"] is not JsonArray a || a.Count != 8)
            {
                var na = new JsonArray();
                for (int i = 0; i < 8; i++) na.Add((JsonNode)null);
                o["limit_bands"] = na;
            }
            if (o["limit_band_weighting"] == null) o["limit_band_weighting"] = "A";
        }

        public static ScenarioDoc CreateNew(string name)
        {
            var asm = Assembly.GetExecutingAssembly();
            using var s = asm.GetManifestResourceStream("NoiseBoxAddin.scenario_template.json");
            using var r = new StreamReader(s);
            var root = JsonNode.Parse(r.ReadToEnd()).AsObject();
            root["name"] = name;
            root["id"] = Guid.NewGuid().ToString("N").Substring(0, 12);
            Stamp(root);
            return new ScenarioDoc(root);
        }

        // Two separate nodes: a JsonNode has one parent, so `a["x"] = a["y"] = value` throws "The node already has a parent".
        private static void Stamp(JsonObject root)
        {
            string now = DateTime.Now.ToString("s");
            root["created"] = now;
            root["modified"] = now;
        }

        public static ScenarioDoc Load(string path)
        {
            var root = JsonNode.Parse(File.ReadAllText(path)).AsObject();
            if ((string)root["schema"] != Schema)
                throw new InvalidDataException($"SCN-003: unsupported scenario schema '{(string)root["schema"]}' (this add-in reads {Schema}).");
            return new ScenarioDoc(root) { FilePath = path };
        }

        public void Save(string path = null)
        {
            path ??= FilePath;
            Root["modified"] = DateTime.Now.ToString("s");
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path)));
            File.WriteAllText(path, Root.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
            FilePath = path;
            Dirty = false;
        }

        public ScenarioDoc Duplicate(string newName)
        {
            var root = JsonNode.Parse(Root.ToJsonString()).AsObject();
            root["id"] = Guid.NewGuid().ToString("N").Substring(0, 12);
            root["name"] = newName;
            Stamp(root);
            return new ScenarioDoc(root) { Dirty = true };
        }

        // ---------------------------------------------------------------- path access
        private static string[] Split(string path) =>
            path.Replace("[", ".[").Split('.', StringSplitOptions.RemoveEmptyEntries);

        public JsonNode Get(string path)
        {
            JsonNode n = Root;
            foreach (var part in Split(path))
            {
                if (n == null) return null;
                if (part.StartsWith("["))
                {
                    int i = int.Parse(part.Trim('[', ']'), CultureInfo.InvariantCulture);
                    n = n is JsonArray a && i < a.Count ? a[i] : null;
                }
                else n = n is JsonObject o && o.ContainsKey(part) ? o[part] : null;
            }
            return n;
        }

        public double? GetDouble(string path)
        {
            var n = Get(path);
            if (n is JsonValue v && v.TryGetValue<double>(out var d)) return d;
            return null;
        }

        public string GetString(string path) => Get(path) is JsonValue v && v.TryGetValue<string>(out var s) ? s : null;
        public bool GetBool(string path, bool def = false) => Get(path) is JsonValue v && v.TryGetValue<bool>(out var b) ? b : def;

        public void Set(string path, JsonNode value)
        {
            var parts = Split(path);
            JsonNode n = Root;
            for (int k = 0; k < parts.Length - 1; k++)
            {
                var part = parts[k];
                if (part.StartsWith("[")) n = n.AsArray()[int.Parse(part.Trim('[', ']'), CultureInfo.InvariantCulture)];
                else
                {
                    var o = n.AsObject();
                    if (o[part] == null) o[part] = new JsonObject();
                    n = o[part];
                }
            }
            var last = parts[^1];
            if (last.StartsWith("[")) n.AsArray()[int.Parse(last.Trim('[', ']'), CultureInfo.InvariantCulture)] = value;
            else n.AsObject()[last] = value;
            Touch();
        }

        public void SetDouble(string path, double? v) => Set(path, v.HasValue ? JsonValue.Create(v.Value) : null);
        public void SetString(string path, string v) => Set(path, v == null ? null : JsonValue.Create(v));
        public void SetBool(string path, bool v) => Set(path, JsonValue.Create(v));

        public void Touch()
        {
            Dirty = true;
            Changed?.Invoke();
        }

        // ---------------------------------------------------------------- the source
        /// <summary>The three ways to define the source all end here: coordinates in the system they were given in.
        /// The conversion to the analysis system happens once, in Python (noisebox/scenario.py).</summary>
        public void SetSourceLocation(string origin, double x, double y, int wkid, JsonNode layer = null)
        {
            Set("source.origin", JsonValue.Create(origin));
            SetDouble("source.x", x);
            SetDouble("source.y", y);
            Set("source.input_wkid", JsonValue.Create(wkid));
            Set("source.layer", layer);
        }

        // ---------------------------------------------------------------- structures
        public JsonArray Structures => Root["structures"] as JsonArray;

        public JsonObject FindStructure(string id) =>
            Structures.OfType<JsonObject>().FirstOrDefault(s => (string)s["id"] == id);

        public int IndexOfStructure(string id)
        {
            for (int i = 0; i < Structures.Count; i++) if ((string)Structures[i]["id"] == id) return i;
            return -1;
        }

        public JsonObject AddStructure(JsonObject s)
        {
            Structures.Add(s);
            Touch();
            return s;
        }

        /// <summary>Removes the object from the scenario. The GIS feature it was made from is untouched.</summary>
        public void RemoveStructure(string id)
        {
            int i = IndexOfStructure(id);
            if (i >= 0) { Structures.RemoveAt(i); Touch(); }
        }

        public JsonObject DuplicateStructure(string id)
        {
            var src = FindStructure(id);
            var copy = JsonNode.Parse(src.ToJsonString()).AsObject();
            copy["id"] = NewId();
            copy["name"] = UniqueName((string)src["name"] + " copy");
            return AddStructure(copy);
        }

        public string UniqueName(string wanted)
        {
            var names = Structures.OfType<JsonObject>().Select(s => (string)s["name"]).ToHashSet();
            if (!names.Contains(wanted)) return wanted;
            for (int i = 2; ; i++) if (!names.Contains($"{wanted} ({i})")) return $"{wanted} ({i})";
        }

        public static string NewId() => Guid.NewGuid().ToString("N").Substring(0, 8);

        // ---------------------------------------------------------------- text <-> value (for bound fields)
        public static bool TryParseNumber(string text, out double v)
        {
            v = 0;
            if (string.IsNullOrWhiteSpace(text)) return false;
            return double.TryParse(text.Trim().Replace(',', '.'), NumberStyles.Float, CultureInfo.InvariantCulture, out v);
        }
    }
}
