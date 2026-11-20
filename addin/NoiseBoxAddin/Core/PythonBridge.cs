using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;

namespace NoiseBoxAddin.Core
{
    /// <summary>One problem found in a scenario (the catalogue is noisebox/issues.py).</summary>
    internal sealed class Issue
    {
        public string Code { get; set; }
        public string Severity { get; set; }   // error | warning | info
        public string Section { get; set; }    // scenario | source | terrain | area | structures | propagation | outputs | engine
        public string Message { get; set; }
        public string Fix { get; set; }
        public string ObjectId { get; set; }
        public string Field { get; set; }

        public string Icon => Severity == "error" ? "⛔" : Severity == "warning" ? "⚠" : "ℹ";
        public string Text => $"{Message}" + (string.IsNullOrEmpty(Fix) ? "" : $"  → {Fix}");

        public static Issue From(JsonNode n) => new Issue
        {
            Code = (string)n["code"], Severity = (string)n["severity"], Section = (string)n["section"],
            Message = (string)n["message"], Fix = (string)n["fix"], ObjectId = (string)n["object_id"], Field = (string)n["field"]
        };

        public static List<Issue> List(JsonNode arr) =>
            (arr as JsonArray)?.Select(From).ToList() ?? new List<Issue>();
    }

    /// <summary>
    /// Calls the Python side (noisebox_cli.py, ArcGIS Pro's propy). The add-in never calculates acoustics and never loads
    /// MATLAB: validation, preview, spectrum parsing and the MATLAB-backed previews are all Python commands that print one
    /// JSON document. The calculation itself runs as the geoprocessing tool NoiseBox.pyt\RunScenario (see ProApi.RunAsync).
    /// </summary>
    internal static class PythonBridge
    {
        /// <summary>Folder that holds noisebox_cli.py: env NOISEBOX_HOME, else %LOCALAPPDATA%\NoiseBox\addin.json (written by
        /// setup\setup_noisebox.ps1), else the folder the add-in was started from.</summary>
        public static string Root()
        {
            var env = Environment.GetEnvironmentVariable("NOISEBOX_HOME");
            if (!string.IsNullOrEmpty(env) && File.Exists(Path.Combine(env, "noisebox_cli.py"))) return env;
            var cfg = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "NoiseBox", "addin.json");
            if (File.Exists(cfg))
            {
                var r = (string)JsonNode.Parse(File.ReadAllText(cfg))["root"];
                if (!string.IsNullOrEmpty(r) && File.Exists(Path.Combine(r, "noisebox_cli.py"))) return r;
            }
            var dir = AppContext.BaseDirectory;
            for (int i = 0; i < 6 && dir != null; i++, dir = Path.GetDirectoryName(dir))
                if (File.Exists(Path.Combine(dir, "noisebox_cli.py"))) return dir;
            throw new FileNotFoundException(
                "The NoiseBox folder was not found (noisebox_cli.py). Run setup\\setup_noisebox.ps1 once, or set the environment variable NOISEBOX_HOME to the NoiseBox folder.");
        }

        private static string Propy()
        {
            var bin = Path.GetDirectoryName(Process.GetCurrentProcess().MainModule.FileName);   // ...\ArcGIS\Pro\bin
            return Path.Combine(bin, "Python", "Scripts", "propy.bat");
        }

        public static string ToolboxPath() => Path.Combine(Root(), "NoiseBox.pyt");

        /// <summary>Runs "propy noisebox_cli.py args" and returns the JSON it prints (last line of stdout).</summary>
        public static Task<JsonObject> CallAsync(params string[] args) => Task.Run(() =>
        {
            var root = Root();
            var psi = new ProcessStartInfo
            {
                FileName = Propy(),
                WorkingDirectory = root,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
            };
            psi.ArgumentList.Add(Path.Combine(root, "noisebox_cli.py"));
            foreach (var a in args) psi.ArgumentList.Add(a);
            using var p = Process.Start(psi);
            string stdout = p.StandardOutput.ReadToEnd();
            string stderr = p.StandardError.ReadToEnd();
            p.WaitForExit();
            var line = stdout.Split('\n').Select(l => l.Trim()).LastOrDefault(l => l.StartsWith("{"));
            if (line == null)
                return new JsonObject { ["ok"] = false, ["error"] = "The NoiseBox Python command returned nothing. " + stderr.Trim() };
            return JsonNode.Parse(line).AsObject();
        });

        /// <summary>Saves the scenario to a temp file (so unsaved edits are checked too) and runs a scenario command on it.</summary>
        public static async Task<JsonObject> OnScenarioAsync(string command, ScenarioDoc doc, params string[] extra)
        {
            var tmp = Path.Combine(Path.GetTempPath(), "noisebox_" + (string)doc.Root["id"] + ".nbscenario.json");
            File.WriteAllText(tmp, doc.Root.ToJsonString());
            return await CallAsync(new[] { command, tmp }.Concat(extra).ToArray());
        }

        public static Task<JsonObject> ValidateAsync(ScenarioDoc doc, bool fast) =>
            OnScenarioAsync("validate", doc, fast ? new[] { "--fast" } : new string[0]);

        /// <summary>fast = no DTM / geodatabase access (used while typing); deep = full check incl. DTM coverage.</summary>
        public static Task<JsonObject> PreviewAsync(ScenarioDoc doc, bool fast = false) =>
            OnScenarioAsync("preview", doc, fast ? new[] { "--fast" } : new string[0]);

        public static Task<JsonObject> ParseSpectrumTextAsync(string text) => CallAsync("parse-spectrum", "--text", text);
        public static Task<JsonObject> ParseSpectrumCsvAsync(string path) => CallAsync("parse-spectrum", "--csv", path);
        public static Task<JsonObject> DtmInfoAsync(string path) => CallAsync("dtm-info", path);
        public static Task<JsonObject> EngineAsync(string action) => CallAsync("engine", action);
        public static Task<JsonObject> AtmosphereAsync(ScenarioDoc doc) => OnScenarioAsync("atmosphere", doc);
        public static Task<JsonObject> MaterialAsync(JsonNode faceMaterial) => CallAsync("material", faceMaterial.ToJsonString());
        public static Task<JsonObject> ProfilesAsync(string action, string name = null, string lw = null)
        {
            var a = new List<string> { "profiles", action };
            if (name != null) { a.Add("--name"); a.Add(name); }
            if (lw != null) { a.Add("--lw"); a.Add(lw); }
            return CallAsync(a.ToArray());
        }
    }
}
