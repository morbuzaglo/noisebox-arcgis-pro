using System;
using System.IO;
using System.Threading.Tasks;
using System.Windows;
using ArcGIS.Desktop.Core;
using ArcGIS.Desktop.Framework;
using ArcGIS.Desktop.Framework.Contracts;
using NoiseBoxAddin.Core;
using NoiseBoxAddin.UI;

namespace NoiseBoxAddin.Buttons
{
    /// <summary>UI-thread helper: map tools run on the Pro main thread (MCT); the pane lives on the WPF thread.</summary>
    internal static class Ui
    {
        public static void Run(Action a) => FrameworkApplication.Current.Dispatcher.Invoke(a);
        public static NoiseBoxPaneViewModel Pane => FrameworkApplication.DockPaneManager.Find("NoiseBox_Pane") as NoiseBoxPaneViewModel;
    }

    internal abstract class PaneButton : Button
    {
        protected static void Open(string section, string focus = null)
        {
            var p = Ui.Pane;
            p?.Activate();
            NoiseBoxPaneViewModel.Show(section, focus);
        }

        protected static Task Tool(string id) => FrameworkApplication.SetCurrentToolAsync(id);
    }

    // ---------------------------------------------------------------- Scenario
    internal class NewScenario : PaneButton
    {
        protected override void OnClick()
        {
            if (NoiseBoxModule.Current.Doc.Dirty &&
                MessageBox.Show("The open scenario has unsaved changes. Start a new one anyway?", "NoiseBox", MessageBoxButton.YesNo) != MessageBoxResult.Yes) return;
            Open("source");
            Ui.Pane?.ReplaceDocument(ScenarioDoc.CreateNew("Scenario 1"));
        }
    }

    internal class OpenScenario : PaneButton
    {
        protected override void OnClick()
        {
            var dlg = new Microsoft.Win32.OpenFileDialog { Filter = "NoiseBox scenario (*.nbscenario.json;*.json)|*.nbscenario.json;*.json", InitialDirectory = Project.Current?.HomeFolderPath };
            if (dlg.ShowDialog() != true) return;
            try
            {
                Open("scenario");
                Ui.Pane?.ReplaceDocument(ScenarioDoc.Load(dlg.FileName));
            }
            catch (Exception e) { MessageBox.Show(e.Message, "NoiseBox: cannot open the scenario"); }
        }
    }

    internal class SaveScenario : PaneButton
    {
        protected override void OnClick()
        {
            var doc = NoiseBoxModule.Current.Doc;
            if (doc.FilePath == null)
            {
                var dlg = new Microsoft.Win32.SaveFileDialog
                {
                    Filter = "NoiseBox scenario (*.nbscenario.json)|*.nbscenario.json", FileName = doc.GetString("name") + ".nbscenario.json",
                    InitialDirectory = Project.Current?.HomeFolderPath,
                };
                if (dlg.ShowDialog() != true) return;
                doc.Save(dlg.FileName);
            }
            else doc.Save();
            if (Ui.Pane != null) Ui.Pane.Status = "Scenario saved: " + doc.FilePath;
        }
    }

    internal class DuplicateScenario : PaneButton
    {
        protected override void OnClick() =>
            Ui.Pane?.ReplaceDocument(NoiseBoxModule.Current.Doc.Duplicate(NoiseBoxModule.Current.Doc.GetString("name") + " copy"));
    }

    // ---------------------------------------------------------------- Source
    internal class SourceFromLayer : PaneButton
    {
        protected override void OnClick() { Open("source"); _ = Ui.Pane?.RefreshListsAsync(); }
    }

    internal class SourceFromCoordinates : PaneButton
    {
        protected override void OnClick()
        {
            Open("source");
            Ui.Pane.ShowCoordinateFields = true;                         // open the coordinate fields ...
            Ui.Pane.ShowSourceCoordinates();
            NoiseBoxPaneViewModel.Show("source", "coordX");              // ... and focus the first one
        }
    }

    internal class SourcePlaceOnMap : PaneButton
    {
        protected override void OnClick()
        {
            Open("source");
            _ = Tool("NoiseBox_PlaceSourceTool");                        // the placement tool is active immediately
        }
    }

    internal class OpenSpectrum : PaneButton { protected override void OnClick() => Open("source", "lw"); }
    internal class OpenDirectivity : PaneButton { protected override void OnClick() => Open("source", "heading"); }

    // ---------------------------------------------------------------- Terrain and Area
    internal class DtmFromProject : PaneButton { protected override void OnClick() { Open("terrain", "dtm"); _ = Ui.Pane?.RefreshListsAsync(); } }
    internal class DtmGround : PaneButton { protected override async void OnClick() { Open("terrain", "dtm"); await Ui.Pane.UseGroundSurfaceAsync(); } }
    internal class DtmBrowse : PaneButton { protected override async void OnClick() { Open("terrain"); await Ui.Pane.BrowseDtmAsync(); } }
    internal class DtmCoverage : PaneButton { protected override void OnClick() { Open("terrain"); Ui.Pane?.ShowCoverageCommand.Execute(null); } }
    internal class DtmNone : PaneButton { protected override void OnClick() { NoiseBoxModule.Current.Doc.Set("terrain.dtm", null); Open("terrain"); } }

    internal class AreaFromPolygons : PaneButton { protected override void OnClick() { Open("terrain", "area"); _ = Ui.Pane?.RefreshListsAsync(); } }
    internal class AreaDrawPolygon : PaneButton { protected override void OnClick() { Open("terrain"); _ = Tool("NoiseBox_AreaPolygonTool"); } }
    internal class AreaDrawRectangle : PaneButton { protected override void OnClick() { Open("terrain"); _ = Tool("NoiseBox_AreaRectangleTool"); } }
    internal class AreaRadius : PaneButton { protected override void OnClick() { Open("terrain", "radius"); Ui.Pane?.UseRadius(); } }
    internal class AreaMapExtent : PaneButton { protected override async void OnClick() { Open("terrain"); await Ui.Pane.CaptureExtentAsync(); } }
    internal class OpenReceiverGrid : PaneButton { protected override void OnClick() => Open("terrain", "cell"); }

    // ---------------------------------------------------------------- Structures
    internal class BuildingFromLayer : PaneButton { protected override void OnClick() { Open("structures"); new ImportWindow("building").ShowDialog(); } }
    internal class BuildingDraw : PaneButton { protected override void OnClick() { Open("structures"); _ = Tool("NoiseBox_BuildingTool"); } }
    internal class BarrierFromLayer : PaneButton { protected override void OnClick() { Open("structures"); new ImportWindow("barrier").ShowDialog(); } }
    internal class BarrierSketch : PaneButton { protected override void OnClick() { Open("structures"); _ = Tool("NoiseBox_BarrierTool"); } }
    internal class BarrierPrecise : PaneButton { protected override void OnClick() { Open("structures"); _ = Tool("NoiseBox_BarrierStartTool"); } }
    internal class EnclosureDraw : PaneButton { protected override void OnClick() { Open("structures"); _ = Tool("NoiseBox_EnclosureTool"); } }

    internal class EnclosureRectangle : PaneButton
    {
        protected override void OnClick()
        {
            Open("structures");
            var e = StructureFactory.RectangleEnclosure("Enclosure", 6.0, 4.0, 3.0);         // quick rectangle around the source
            Ui.Pane?.AddStructure(e);
            NoiseBoxPaneViewModel.Show("structures", "sname");
        }
    }

    // ---------------------------------------------------------------- Propagation
    internal class OpenGround : PaneButton { protected override void OnClick() => Open("propagation", "G"); }
    internal class OpenAtmosphere : PaneButton { protected override void OnClick() => Open("propagation", "T"); }
    internal class OpenTerrainScreening : PaneButton { protected override void OnClick() => Open("propagation"); }
    internal class OpenMeteorology : PaneButton { protected override void OnClick() => Open("propagation", "C0"); }

    // ---------------------------------------------------------------- Analysis
    internal class Preview : PaneButton { protected override void OnClick() { Open("issues"); Ui.Pane?.PreviewCommand.Execute(null); } }
    internal class Run : PaneButton { protected override void OnClick() { Open("issues"); Ui.Pane?.RunCommand.Execute(null); } }
    internal class OpenResults : PaneButton { protected override void OnClick() => Open("outputs"); }
}
