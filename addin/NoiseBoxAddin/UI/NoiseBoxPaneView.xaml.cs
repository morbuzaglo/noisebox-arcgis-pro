using System;
using System.Collections;
using System.Collections.Generic;
using System.Collections.Specialized;
using System.Globalization;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Input;
using System.Windows.Media;

namespace NoiseBoxAddin.UI
{
    /// <summary>Value converters used by the pane (static instances, referenced as ui:Inverse.X in the XAML).</summary>
    internal sealed class BoolConv : IValueConverter
    {
        private readonly Func<bool, object> _to;
        private readonly bool _invert;
        public BoolConv(Func<bool, object> to, bool invert = false) { _to = to; _invert = invert; }
        public object Convert(object v, Type t, object p, CultureInfo c) => _to(v is bool b && b);
        public object ConvertBack(object v, Type t, object p, CultureInfo c) => _invert ? !(v is bool b && b) : Binding.DoNothing;
    }

    internal sealed class CountConv : IValueConverter
    {
        public object Convert(object v, Type t, object p, CultureInfo c) => v is int n && n > 0 ? Visibility.Visible : Visibility.Collapsed;
        public object ConvertBack(object v, Type t, object p, CultureInfo c) => Binding.DoNothing;
    }

    internal static class Inverse
    {
        public static readonly IValueConverter Bool = new BoolConv(b => !b, true);
        public static readonly IValueConverter BoolVisibility = new BoolConv(b => b ? Visibility.Visible : Visibility.Collapsed);
        public static readonly IValueConverter BoolNotVisibility = new BoolConv(b => b ? Visibility.Collapsed : Visibility.Visible);
        public static readonly IValueConverter CountVisibility = new CountConv();
    }

    public partial class NoiseBoxPaneView : UserControl
    {
        public NoiseBoxPaneView()
        {
            InitializeComponent();
            DataContextChanged += (s, e) =>
            {
                if (e.NewValue is NoiseBoxPaneViewModel vm) vm.FocusRequested += FocusField;
            };
        }

        private NoiseBoxPaneViewModel VM => DataContext as NoiseBoxPaneViewModel;

        /// <summary>Moves the keyboard focus to the named input (x:Name = "f_" + key) and scrolls it into view.</summary>
        private void FocusField(string key)
        {
            if (FindName("f_" + key) is FrameworkElement el)
                Dispatcher.BeginInvoke(new Action(() => { el.BringIntoView(); el.Focus(); Keyboard.Focus(el); }), System.Windows.Threading.DispatcherPriority.Background);
        }

        private async void Lw_PreviewKeyDown(object sender, KeyEventArgs e)
        {
            if (e.Key == Key.V && Keyboard.Modifiers == ModifierKeys.Control && VM != null)
            {
                e.Handled = true;
                await VM.PasteSpectrumAsync(Clipboard.GetText());
            }
        }

        private void Issue_Selected(object sender, SelectionChangedEventArgs e)
        {
            if (VM?.SelectedIssue != null) VM.GoTo(VM.SelectedIssue);
        }

        private void Issue_DoubleClick(object sender, MouseButtonEventArgs e)
        {
            if (VM?.SelectedIssue != null) VM.GoTo(VM.SelectedIssue);
        }
    }

    /// <summary>Small bar plot of the spectrum. A missing band is a hollow marker on the baseline, not a bar at 0 dB.</summary>
    public sealed class SpectrumPlot : FrameworkElement
    {
        public static readonly DependencyProperty RowsProperty = DependencyProperty.Register(nameof(Rows), typeof(IEnumerable), typeof(SpectrumPlot),
            new FrameworkPropertyMetadata(null, FrameworkPropertyMetadataOptions.AffectsRender));
        public static readonly DependencyProperty VersionProperty = DependencyProperty.Register(nameof(Version), typeof(int), typeof(SpectrumPlot),
            new FrameworkPropertyMetadata(0, FrameworkPropertyMetadataOptions.AffectsRender));

        public IEnumerable Rows { get => (IEnumerable)GetValue(RowsProperty); set => SetValue(RowsProperty, value); }
        public int Version { get => (int)GetValue(VersionProperty); set => SetValue(VersionProperty, value); }

        protected override void OnRender(DrawingContext dc)
        {
            double w = ActualWidth, h = ActualHeight;
            dc.DrawRectangle(Brushes.Transparent, new Pen(Brushes.Gray, 0.5), new Rect(0, 0, w, h));
            var rows = Rows?.Cast<object>().Select(r => (dynamic)r).ToList();
            if (rows == null || rows.Count == 0) return;
            var vals = rows.Select(r => double.TryParse(((string)r.Text).Replace(',', '.'), NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : (double?)null).ToList();
            double lo = Math.Min(0, vals.Where(v => v.HasValue).Select(v => v.Value).DefaultIfEmpty(0).Min());
            double hi = Math.Max(10, vals.Where(v => v.HasValue).Select(v => v.Value).DefaultIfEmpty(0).Max());
            double bw = w / vals.Count;
            for (int i = 0; i < vals.Count; i++)
            {
                double x = i * bw + bw * 0.15;
                if (vals[i].HasValue)
                {
                    double top = h - 12 - (vals[i].Value - lo) / (hi - lo) * (h - 18);
                    dc.DrawRectangle(Brushes.SteelBlue, null, new Rect(x, top, bw * 0.7, Math.Max(1, h - 12 - top)));
                }
                else dc.DrawEllipse(null, new Pen(Brushes.Firebrick, 1.5), new Point(x + bw * 0.35, h - 14), 3, 3);          // missing
                var ft = new FormattedText(((int)rows[i].Hz).ToString(), CultureInfo.InvariantCulture, FlowDirection.LeftToRight, new Typeface("Segoe UI"), 8, Brushes.Gray, 1.0);
                dc.DrawText(ft, new Point(x, h - 11));
            }
        }
    }

    /// <summary>Ground and barrier top along a barrier (profile preview).</summary>
    public sealed class ProfilePlot : FrameworkElement
    {
        public static readonly DependencyProperty DataProperty = DependencyProperty.Register(nameof(Data), typeof(IEnumerable), typeof(ProfilePlot),
            new FrameworkPropertyMetadata(null, FrameworkPropertyMetadataOptions.AffectsRender, (d, e) =>
            {
                if (e.NewValue is INotifyCollectionChanged n) n.CollectionChanged += (s, a) => ((ProfilePlot)d).InvalidateVisual();
            }));

        public IEnumerable Data { get => (IEnumerable)GetValue(DataProperty); set => SetValue(DataProperty, value); }

        protected override void OnRender(DrawingContext dc)
        {
            double w = ActualWidth, h = ActualHeight;
            dc.DrawRectangle(Brushes.Transparent, new Pen(Brushes.Gray, 0.5), new Rect(0, 0, w, h));
            var pts = Data?.Cast<ProfilePoint>().ToList();
            if (pts == null || pts.Count < 2) return;
            double smax = pts.Max(p => p.S);
            double zmin = pts.Min(p => Math.Min(p.Ground ?? p.Top, p.Top)) - 1, zmax = pts.Max(p => p.Top) + 1;
            Func<double, double> X = s => 4 + s / Math.Max(smax, 1e-9) * (w - 8);
            Func<double, double> Y = z => h - 4 - (z - zmin) / Math.Max(zmax - zmin, 1e-9) * (h - 8);
            for (int i = 1; i < pts.Count; i++)
            {
                if (pts[i - 1].Ground.HasValue && pts[i].Ground.HasValue)
                    dc.DrawLine(new Pen(Brushes.SaddleBrown, 2), new Point(X(pts[i - 1].S), Y(pts[i - 1].Ground.Value)), new Point(X(pts[i].S), Y(pts[i].Ground.Value)));
                dc.DrawLine(new Pen(Brushes.SteelBlue, 2), new Point(X(pts[i - 1].S), Y(pts[i - 1].Top)), new Point(X(pts[i].S), Y(pts[i].Top)));
            }
        }
    }
}
