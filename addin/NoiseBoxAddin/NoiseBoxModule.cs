using ArcGIS.Desktop.Framework;
using ArcGIS.Desktop.Framework.Contracts;
using NoiseBoxAddin.Core;

namespace NoiseBoxAddin
{
    /// <summary>The add-in module. Holds the scenario that is open (one at a time) and its overlay on the map.</summary>
    internal class NoiseBoxModule : Module
    {
        private static NoiseBoxModule _this;

        public static NoiseBoxModule Current => _this ??= (NoiseBoxModule)FrameworkApplication.FindModule("NoiseBox_Module");

        /// <summary>The open scenario. Edited by the pane and the map tools; written to disk by Save.</summary>
        public ScenarioDoc Doc { get; set; } = ScenarioDoc.CreateNew("Scenario 1");

        /// <summary>Result of the last Preview (source, area, gaps, issues); drives the map overlay.</summary>
        public System.Text.Json.Nodes.JsonObject LastPreview { get; set; }

        protected override bool CanUnload() => true;
    }
}
