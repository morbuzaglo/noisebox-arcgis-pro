using System;
using System.IO;
using ArcGIS.Desktop.Framework;
using ArcGIS.Desktop.Framework.Contracts;
using NoiseBoxAddin.Core;

namespace NoiseBoxAddin
{
    /// <summary>Writes every exception raised inside this add-in to %LOCALAPPDATA%\NoiseBox\addin.log, so a failure that ArcGIS
    /// Pro swallows (a greyed-out button, a pane that does not open) can still be diagnosed.</summary>
    internal static class Log
    {
        private static readonly string PathName = System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "NoiseBox", "addin.log");
        private static bool _hooked;
        private static readonly object Gate = new object();

        public static void Write(string text)
        {
            try
            {
                lock (Gate)
                {
                    Directory.CreateDirectory(System.IO.Path.GetDirectoryName(PathName));
                    File.AppendAllText(PathName, DateTime.Now.ToString("s") + "  " + text + Environment.NewLine);
                }
            }
            catch { /* logging must never throw */ }
        }

        public static void Hook()
        {
            if (_hooked) return;
            _hooked = true;
            AppDomain.CurrentDomain.FirstChanceException += (s, e) =>
            {
                try
                {
                    var ex = e.Exception;
                    string st = ex.StackTrace ?? "";
                    string all = ex.ToString();
                    if (st.Contains("NoiseBoxAddin") || ex is System.Windows.Markup.XamlParseException || all.Contains("NoiseBoxAddin"))
                        Write("EXCEPTION " + all);
                }
                catch { }
            };
            Write("add-in loaded (log started)");
        }
    }

    /// <summary>The add-in module. Holds the scenario that is open (one at a time) and its overlay on the map.</summary>
    internal class NoiseBoxModule : Module
    {
        private static NoiseBoxModule _this;

        public NoiseBoxModule() { Log.Hook(); }

        public static NoiseBoxModule Current => _this ??= (NoiseBoxModule)FrameworkApplication.FindModule("NoiseBox_Module");

        /// <summary>The open scenario. Edited by the pane and the map tools; written to disk by Save.</summary>
        public ScenarioDoc Doc { get; set; } = ScenarioDoc.CreateNew("Scenario 1");

        /// <summary>Result of the last Preview (source, area, gaps, issues); drives the map overlay.</summary>
        public System.Text.Json.Nodes.JsonObject LastPreview { get; set; }

        protected override bool CanUnload() => true;
    }
}
