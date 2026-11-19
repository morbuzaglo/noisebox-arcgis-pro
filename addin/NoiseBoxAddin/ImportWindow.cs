using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using ArcGIS.Core.CIM;
using ArcGIS.Core.Data;
using Orientation = System.Windows.Controls.Orientation;
using HorizontalAlignment = System.Windows.HorizontalAlignment;
using ArcGIS.Core.Geometry;
using ArcGIS.Desktop.Framework;
using ArcGIS.Desktop.Framework.Controls;
using ArcGIS.Desktop.Framework.Threading.Tasks;
using ArcGIS.Desktop.Mapping;
using NoiseBoxAddin.Buttons;
using NoiseBoxAddin.Core;

namespace NoiseBoxAddin
{
    /// <summary>
    /// Import buildings (polygons) or noise barriers (polylines) from a layer: selected features or the entire layer, one
    /// height for all or read from a numeric field, with the unit stated and the imported values previewed before anything is
    /// added. The GIS features themselves are never edited; the scenario keeps a copy of their geometry.
    /// </summary>
    internal class ImportWindow : ProWindow
    {
        private readonly string _kind;
        private readonly ComboBox _layers = new ComboBox { Margin = new Thickness(0, 2, 0, 6) };
        private readonly RadioButton _selected = new RadioButton { Content = "Selected features", IsChecked = true, Margin = new Thickness(0, 0, 12, 0) };
        private readonly RadioButton _all = new RadioButton { Content = "Entire layer" };
        private readonly RadioButton _single = new RadioButton { Content = "One height for all", IsChecked = true };
        private readonly RadioButton _fromField = new RadioButton { Content = "Read from field" };
        private readonly TextBox _height = new TextBox { Margin = new Thickness(0, 2, 0, 4) };
        private readonly ComboBox _fields = new ComboBox { Margin = new Thickness(0, 2, 0, 4) };
        private readonly ComboBox _unit = new ComboBox { ItemsSource = new[] { "metres", "feet" }, SelectedIndex = 0, Margin = new Thickness(0, 2, 0, 4) };
        private readonly ListBox _preview = new ListBox { Height = 130, Margin = new Thickness(0, 4, 0, 4) };
        private readonly TextBlock _note = new TextBlock { TextWrapping = TextWrapping.Wrap, Foreground = System.Windows.Media.Brushes.Gray };
        private readonly List<(long oid, string name, List<double[]> pts, double? raw)> _rows = new List<(long, string, List<double[]>, double?)>();
        private int _wkid;

        public ImportWindow(string kind)
        {
            _kind = kind;
            Title = kind == "building" ? "Add Buildings from a Layer" : "Add Noise Barriers from a Layer";
            Width = 420; Height = 560;
            Owner = FrameworkApplication.Current.MainWindow;
            WindowStartupLocation = WindowStartupLocation.CenterOwner;

            var p = new StackPanel { Margin = new Thickness(10) };
            p.Children.Add(new TextBlock { Text = kind == "building" ? "Polygon layer" : "Polyline layer" });
            p.Children.Add(_layers);
            var src = new StackPanel { Orientation = Orientation.Horizontal };
            src.Children.Add(_selected); src.Children.Add(_all);
            p.Children.Add(src);
            p.Children.Add(new TextBlock { Text = kind == "building" ? "Height above ground" : "Height above local terrain", Margin = new Thickness(0, 8, 0, 2), FontWeight = FontWeights.SemiBold });
            p.Children.Add(_single);
            p.Children.Add(_height);
            p.Children.Add(_fromField);
            p.Children.Add(_fields);
            p.Children.Add(new TextBlock { Text = "Unit of the height (the field has no unit of its own)" });
            p.Children.Add(_unit);
            var prev = new Button { Content = "Preview values", HorizontalAlignment = System.Windows.HorizontalAlignment.Left, Padding = new Thickness(8, 2, 8, 2) };
            prev.Click += async (s, e) => await LoadAsync();
            p.Children.Add(prev);
            p.Children.Add(_preview);
            p.Children.Add(_note);
            var ok = new Button { Content = "Add to scenario", Margin = new Thickness(0, 8, 8, 0), Padding = new Thickness(10, 3, 10, 3), IsDefault = true };
            ok.Click += async (s, e) => { if (await LoadAsync()) { Import(); Close(); } };
            var cancel = new Button { Content = "Cancel", Margin = new Thickness(0, 8, 0, 0), Padding = new Thickness(10, 3, 10, 3), IsCancel = true };
            var row = new StackPanel { Orientation = Orientation.Horizontal };
            row.Children.Add(ok); row.Children.Add(cancel);
            p.Children.Add(row);
            Content = p;

            Loaded += async (s, e) =>
            {
                var shape = kind == "building" ? esriGeometryType.esriGeometryPolygon : esriGeometryType.esriGeometryPolyline;
                _layers.ItemsSource = await ProApi.LayersAsync(shape);
                _layers.DisplayMemberPath = "Name";
                _layers.SelectionChanged += async (a, b) => await FillFieldsAsync();
                if (_layers.Items.Count > 0) _layers.SelectedIndex = 0;
            };
        }

        private FeatureLayer Layer => (_layers.SelectedItem as LayerItem)?.Layer as FeatureLayer;

        private async Task FillFieldsAsync()
        {
            var fl = Layer;
            if (fl == null) return;
            var names = await QueuedTask.Run(() => fl.GetFeatureClass().GetDefinition().GetFields()
                .Where(f => f.FieldType is FieldType.Double or FieldType.Single or FieldType.Integer or FieldType.SmallInteger or FieldType.BigInteger)
                .Select(f => f.Name).ToList());
            _fields.ItemsSource = names;
            var guess = names.FirstOrDefault(n => n.ToLower().Contains("height") || n.ToLower() == "h" || n.ToLower().Contains("hgt") || n.ToLower().Contains("elev"));
            if (guess != null) _fields.SelectedItem = guess;
        }

        private async Task<bool> LoadAsync()
        {
            var fl = Layer;
            if (fl == null) { _note.Text = "Choose a layer."; return false; }
            string field = _fromField.IsChecked == true ? _fields.SelectedItem as string : null;
            if (_fromField.IsChecked == true && field == null) { _note.Text = "Choose the height field (BLD-007)."; return false; }
            bool selOnly = _selected.IsChecked == true;
            _rows.Clear();
            var (rows, wkid) = await QueuedTask.Run(() =>
            {
                var list = new List<(long, string, List<double[]>, double?)>();
                var filter = new QueryFilter();
                if (selOnly) filter.ObjectIDs = fl.GetSelection().GetObjectIDs();
                int w = ProApi.Wkid(fl.GetSpatialReference());
                using var cur = fl.Search(filter);
                while (cur.MoveNext())
                {
                    using var f = cur.Current as Feature;
                    var shape = f?.GetShape();
                    List<double[]> pts = shape is Polygon pg && pg.PartCount > 0 ? ProApi.Points(pg) : shape is Polyline pl && pl.PartCount > 0 ? ProApi.Points(pl) : null;
                    if (pts == null) continue;
                    double? raw = null;
                    if (field != null) { var v = f[field]; if (v != null && v != DBNull.Value) raw = Convert.ToDouble(v); }
                    list.Add((f.GetObjectID(), $"{fl.Name} {f.GetObjectID()}", pts, raw));
                }
                return (list, w);
            });
            _rows.AddRange(rows);
            _wkid = wkid;
            if (_rows.Count == 0) { _note.Text = selOnly ? $"No feature is selected in {fl.Name}. Select features, or choose Entire layer." : "The layer has no features."; return false; }
            double f2m = (string)_unit.SelectedItem == "feet" ? 0.3048 : 1.0;
            _preview.ItemsSource = _rows.Select(r => $"ID {r.oid}: " + (HeightOf(r.raw, f2m) is double h ? $"{h:0.##} m" : "no height")).ToList();
            int missing = _rows.Count(r => HeightOf(r.raw, f2m) == null);
            _note.Text = $"{_rows.Count} feature(s). " + (missing > 0 ? $"{missing} without a height: they are added and flagged in the issue list (BLD-004 / BAR-004). " : "") +
                         (field != null ? $"Field '{field}' read as {(string)_unit.SelectedItem}." : "");
            return true;
        }

        private double? HeightOf(double? raw, double f2m)
        {
            if (_fromField.IsChecked == true) return raw * f2m;
            return ScenarioDoc.TryParseNumber(_height.Text, out var h) ? h * f2m : (double?)null;
        }

        private void Import()
        {
            double f2m = (string)_unit.SelectedItem == "feet" ? 0.3048 : 1.0;
            var fl = Layer;
            Ui.Run(() =>
            {
                foreach (var r in _rows)
                {
                    var layerRef = ProApi.LayerRef(fl, r.oid);
                    var h = HeightOf(r.raw, f2m);
                    var s = _kind == "building"
                        ? StructureFactory.Building(r.name, r.pts, _wkid, h, layerRef)
                        : StructureFactory.Barrier(r.name, r.pts, _wkid, h, layerRef);
                    if (_kind == "building" && _fromField.IsChecked == true)
                        s["height_source"] = new JsonObject { ["mode"] = "field", ["field"] = _fields.SelectedItem as string, ["unit"] = (string)_unit.SelectedItem };
                    Ui.Pane?.AddStructure(s);
                }
            });
        }
    }
}
