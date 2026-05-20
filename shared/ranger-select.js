/* ============================================================
   Ranger Dashboards — Shared <select> auto-styler

   Walks every <select> on the page once on DOMContentLoaded and
   adds the `.ranger-select` class so the shared CSS applies,
   *unless* the element opts out by carrying:
     - the class `no-ranger-select`
     - a data attribute `data-no-ranger-select`
     - or already has the class

   This lets dashboards adopt the standard styling without editing
   every <select> tag. Selects added dynamically can be picked up
   by calling RangerSelect.refresh() after the DOM mutates.
   ============================================================ */
(function (global) {
  'use strict';

  function shouldSkip(el) {
    if (!el || el.tagName !== 'SELECT') return true;
    if (el.classList.contains('ranger-select')) return true;
    if (el.classList.contains('no-ranger-select')) return true;
    if (el.hasAttribute('data-no-ranger-select')) return true;
    // Skip selects inside a Leaflet popup / Chart.js tooltip container
    if (el.closest && (el.closest('.leaflet-popup') || el.closest('.chartjs-tooltip'))) return true;
    return false;
  }

  function decorate() {
    var sels = document.getElementsByTagName('select');
    for (var i = 0; i < sels.length; i++) {
      if (shouldSkip(sels[i])) continue;
      sels[i].classList.add('ranger-select');
    }
  }

  function init() { decorate(); }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  global.RangerSelect = { init: init, refresh: decorate };
})(window);
