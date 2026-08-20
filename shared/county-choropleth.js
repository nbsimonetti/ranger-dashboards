/* ============================================================
   Ranger Dashboards — Shared county choropleth (Leaflet)

   Fills Texas county polygons with a colour gradient driven by a
   measured value, instead of dropping a proxy dot on each county.

   USAGE:
     const ch = await CountyChoropleth.render({
       map,                       // Leaflet map
       values: {'48113': 1831012, ...},   // keyed by 5-digit county FIPS
       ramp: 'navy',              // navy | gold | risk | vitality  (or [[t,[r,g,b]],…])
       label: 'Employment',
       format: v => v.toLocaleString(),
       popup: (fips, val, name) => '<b>'+name+'</b>…',   // optional
       legendEl: document.getElementById('map-legend'),  // optional
       bins: 6,                   // quantile bins (equal-count); 0 = linear
       fit: true,                 // fit map to the drawn counties
     });
     ch.update(newValues, {ramp, label, format});  // recolour in place
     ch.layer                                       // the L.geoJSON layer

   Why quantile bins by default: county metrics are heavily skewed (Harris
   dwarfs the rural counties), so a linear ramp renders all but a few counties
   the same pale tint. Equal-count bins keep the map readable; pass bins:0 for
   a true linear ramp when the data is evenly spread.
   ============================================================ */
(function (global) {
  'use strict';

  var GEOJSON_URL = 'https://nbsimonetti.github.io/ranger-dashboards/shared/tx-counties.geojson';
  var _cache = null;

  // Sequential single-hue ramps for magnitude; semantic ramps for rates.
  var RAMPS = {
    navy:     [[0, [234, 240, 245]], [0.5, [78, 121, 150]], [1, [1, 42, 82]]],
    gold:     [[0, [247, 240, 228]], [0.5, [203, 153, 92]], [1, [140, 98, 57]]],
    steel:    [[0, [231, 237, 243]], [0.5, [79, 137, 176]], [1, [27, 94, 140]]],
    risk:     [[0, [47, 125, 93]], [0.5, [181, 118, 31]], [1, [218, 12, 27]]],   // good -> bad
    vitality: [[0, [218, 12, 27]], [0.5, [181, 118, 31]], [1, [47, 125, 93]]],   // bad -> good
  };
  var NO_DATA = '#E6E1D7';
  var BORDER = '#FFFFFF';

  function rampOf(r) {
    if (Array.isArray(r)) return r;
    return RAMPS[r] || RAMPS.navy;
  }

  function colorAt(ramp, t) {
    t = Math.max(0, Math.min(1, t));
    var a = ramp[0], b = ramp[ramp.length - 1];
    for (var i = 0; i < ramp.length - 1; i++) {
      if (t >= ramp[i][0] && t <= ramp[i + 1][0]) { a = ramp[i]; b = ramp[i + 1]; break; }
    }
    var span = (b[0] - a[0]) || 1, k = (t - a[0]) / span;
    var c = [0, 1, 2].map(function (j) { return Math.round(a[1][j] + (b[1][j] - a[1][j]) * k); });
    return 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')';
  }

  /* Tie-aware percentile rank (midrank ECDF) -> 0..1.
     Hard quantile bins collapse on tied data — bank counts are mostly 0/1/2, so
     cut-based binning produced only three shades. Ranking by the share of counties
     below each value keeps skewed, tie-heavy metrics readable while still giving
     equal values an equal colour. */
  function ranker(vals) {
    var s = vals.slice().sort(function (x, y) { return x - y; });
    var n = s.length;
    function lower(v) { var lo = 0, hi = n; while (lo < hi) { var m = (lo + hi) >> 1; if (s[m] < v) lo = m + 1; else hi = m; } return lo; }
    function upper(v) { var lo = 0, hi = n; while (lo < hi) { var m = (lo + hi) >> 1; if (s[m] <= v) lo = m + 1; else hi = m; } return lo; }
    return function (v) { return n ? ((lower(v) + upper(v)) / 2) / n : 0.5; };
  }

  function loadGeo() {
    if (_cache) return Promise.resolve(_cache);
    // try the local copy first so it works offline / on a local server
    return fetch('../shared/tx-counties.geojson')
      .then(function (r) { if (!r.ok) throw new Error('local miss'); return r.json(); })
      .catch(function () { return fetch(GEOJSON_URL).then(function (r) { return r.json(); }); })
      .then(function (g) { _cache = g; return g; });
  }

  function render(opts) {
    return loadGeo().then(function (geo) {
      var state = {
        values: opts.values || {},
        ramp: rampOf(opts.ramp),
        label: opts.label || '',
        format: opts.format || function (v) { return String(v); },
        bins: opts.bins == null ? 6 : opts.bins,
        popup: opts.popup,
      };

      function scale() {
        var vals = [];
        for (var k in state.values) {
          var v = state.values[k];
          if (v != null && isFinite(v)) vals.push(v);
        }
        if (!vals.length) return { t: function () { return null; }, min: null, max: null, cuts: [] };
        var min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
        if (state.bins > 0) {
          var rank = ranker(vals);
          return {
            min: min, max: max, cuts: [],
            t: function (v) {
              if (v == null || !isFinite(v)) return null;
              return rank(v);
            },
          };
        }
        return {
          min: min, max: max, cuts: [],
          t: function (v) {
            if (v == null || !isFinite(v)) return null;
            return max === min ? 0.5 : (v - min) / (max - min);
          },
        };
      }

      var sc = scale();

      function fillFor(fips) {
        var t = sc.t(state.values[fips]);
        return t == null ? NO_DATA : colorAt(state.ramp, t);
      }

      function styleFn(f) {
        return {
          fillColor: fillFor(f.properties.fips),
          weight: 0.7, color: BORDER, opacity: 1, fillOpacity: 0.88,
        };
      }

      var layer = L.geoJSON(geo, {
        style: styleFn,
        onEachFeature: function (f, lyr) {
          var fips = f.properties.fips, name = f.properties.name;
          function html() {
            if (state.popup) return state.popup(fips, state.values[fips], name);
            var v = state.values[fips];
            return '<b>' + name + ' County</b><br>' + state.label + ': <b>' +
              (v == null ? 'no data' : state.format(v)) + '</b>';
          }
          lyr.bindPopup(html);
          lyr.bindTooltip(function () { return html(); }, { sticky: true });
          lyr.on('mouseover', function () {
            lyr.setStyle({ weight: 2.2, color: '#012A52' });
            if (lyr.bringToFront) lyr.bringToFront();
          });
          lyr.on('mouseout', function () { lyr.setStyle({ weight: 0.7, color: BORDER }); });
        },
      }).addTo(opts.map);

      if (opts.fit !== false) {
        try { opts.map.fitBounds(layer.getBounds(), { padding: [16, 16] }); } catch (e) {}
      }

      function drawLegend() {
        if (!opts.legendEl) return;
        var stops = [];
        for (var i = 0; i <= 10; i++) stops.push(colorAt(state.ramp, i / 10));
        var withData = 0;
        for (var k in state.values) if (state.values[k] != null && isFinite(state.values[k])) withData++;
        opts.legendEl.innerHTML =
          '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:12px">' +
            '<span style="font-weight:600">' + state.label + '</span>' +
            '<span>' + (sc.min == null ? '' : state.format(sc.min)) + '</span>' +
            '<span style="display:inline-block;width:170px;height:11px;border-radius:3px;' +
              'border:1px solid #DDD8CE;background:linear-gradient(90deg,' + stops.join(',') + ')"></span>' +
            '<span>' + (sc.max == null ? '' : state.format(sc.max)) + '</span>' +
            '<span style="display:inline-flex;align-items:center;gap:5px;margin-left:6px">' +
              '<span style="width:12px;height:12px;border-radius:3px;background:' + NO_DATA +
              ';border:1px solid #DDD8CE;display:inline-block"></span>no data</span>' +
            '<span style="color:#8B9199">' + withData + ' of 254 counties' +
              (state.bins > 0 ? ' · shaded by rank' : ' · linear shading') + '</span>' +
          '</div>';
      }
      drawLegend();

      return {
        layer: layer,
        update: function (values, o) {
          o = o || {};
          if (values) state.values = values;
          if (o.ramp) state.ramp = rampOf(o.ramp);
          if (o.label) state.label = o.label;
          if (o.format) state.format = o.format;
          if (o.bins != null) state.bins = o.bins;
          if (o.popup) state.popup = o.popup;
          sc = scale();
          layer.setStyle(styleFn);
          drawLegend();
        },
      };
    });
  }

  global.CountyChoropleth = { render: render, RAMPS: RAMPS };
})(window);
