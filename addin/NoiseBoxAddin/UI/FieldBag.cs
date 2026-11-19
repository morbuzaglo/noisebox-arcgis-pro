using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Text.Json.Nodes;
using NoiseBoxAddin.Core;

namespace NoiseBoxAddin.UI
{
    /// <summary>One value of the scenario, bound as text. An empty box is a missing value (null in the JSON), which is not
    /// the same as 0. Typing writes straight into the scenario; the map overlay and the issue list follow.</summary>
    internal sealed class Field : INotifyPropertyChanged
    {
        private readonly Func<ScenarioDoc> _doc;
        private readonly Func<string> _path;
        private readonly bool _numeric;
        public event PropertyChangedEventHandler PropertyChanged;

        public Field(Func<ScenarioDoc> doc, Func<string> path, bool numeric)
        {
            _doc = doc; _path = path; _numeric = numeric;
        }

        public string Text
        {
            get
            {
                var p = _path();
                if (p == null) return "";
                var n = _doc().Get(p);
                if (n == null) return "";
                if (_numeric) { var d = _doc().GetDouble(p); return d.HasValue ? d.Value.ToString("0.######", System.Globalization.CultureInfo.InvariantCulture) : ""; }
                return n.ToString().Trim('"');
            }
            set
            {
                var p = _path();
                if (p == null) return;
                if (_numeric)
                {
                    if (string.IsNullOrWhiteSpace(value)) _doc().SetDouble(p, null);
                    else if (ScenarioDoc.TryParseNumber(value, out var d)) _doc().SetDouble(p, d);
                    else _doc().SetString(p, value);          // kept as text so validation can say "not a number"
                }
                else _doc().SetString(p, string.IsNullOrEmpty(value) ? null : value);
                PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(Text)));
            }
        }

        public void Refresh() => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(Text)));
    }

    /// <summary>Indexer so XAML can bind to {Binding F[height].Text}. Keys are registered by the view model.</summary>
    internal sealed class FieldBag
    {
        private readonly Dictionary<string, Field> _f = new Dictionary<string, Field>();
        private readonly Func<ScenarioDoc> _doc;

        public FieldBag(Func<ScenarioDoc> doc) { _doc = doc; }

        public void Num(string key, string path) => _f[key] = new Field(_doc, () => path, true);
        public void Str(string key, string path) => _f[key] = new Field(_doc, () => path, false);
        public void NumDyn(string key, Func<string> path) => _f[key] = new Field(_doc, path, true);
        public void StrDyn(string key, Func<string> path) => _f[key] = new Field(_doc, path, false);

        public Field this[string key] => _f[key];

        public void RefreshAll() { foreach (var f in _f.Values) f.Refresh(); }
    }
}
