/* ============================================================
   Ranger Dashboards — keep Plotly charts inside their container

   Plotly sizes a chart when it is drawn and then leaves it alone. Two situations
   in this suite produce a chart that is wider than the panel holding it, which
   scrolls the whole page sideways:

     1. the chart is drawn while its tab is hidden (display:none), so it measures
        a zero/º stale container and falls back to a default width;
     2. the viewport changes after the chart was drawn.

   Dropping this file into a dashboard re-fits every VISIBLE plot after a tab
   switch, a window resize, or first paint. It is generic and idempotent — no
   per-dashboard wiring, and safe to include alongside a dashboard's own resize
   handling.
   ============================================================ */
(function () {
  'use strict';

  function refit() {
    if (!window.Plotly || !Plotly.Plots || !Plotly.Plots.resize) return;
    document.querySelectorAll('.js-plotly-plot').forEach(function (el) {
      // offsetParent is null for anything inside a display:none tab
      if (el.offsetParent === null) return;
      if (!el.getBoundingClientRect().width) return;
      try { Plotly.Plots.resize(el); } catch (e) { /* chart torn down mid-flight */ }
    });
  }

  var t;
  window.addEventListener('resize', function () {
    clearTimeout(t);
    t = setTimeout(refit, 180);
  });

  // Tab switches are plain clicks in this suite; catch them on the way down so we
  // run after the view has been revealed.
  document.addEventListener('click', function (e) {
    var el = e.target;
    if (!el || !el.closest) return;
    if (el.closest('nav button, [data-view], .tab, .tabbtn')) setTimeout(refit, 80);
  }, true);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { setTimeout(refit, 300); });
  } else {
    setTimeout(refit, 300);
  }
  window.addEventListener('load', function () { setTimeout(refit, 200); });

  window.RangerChartFit = { refit: refit };
})();
