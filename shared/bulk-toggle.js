/* ============================================================
   Ranger Dashboards — Shared Bulk Checkbox Toggle

   Drop-in utility for filter groups that contain multiple
   checkboxes (e.g. counties, property types, specialties).

   USAGE — declarative (recommended):

     <div class="ft">
       County
       <span class="bt-actions"
             data-bt-group=".ccd"          (selector for the checkboxes)
             data-bt-after="applyFilters"  (function to call once after bulk toggle)>
       </span>
     </div>

     Then call BulkToggle.init() once on page load. It walks every
     [data-bt-group] element, injects the All / None buttons inside,
     and keeps their disabled state in sync with the live checkbox
     state. Newly-added groups can be picked up via BulkToggle.refresh().

   USAGE — programmatic (if templating is awkward):

     BulkToggle.set('.ccd', true);   // check all
     BulkToggle.set('.ccd', false);  // uncheck all

   The bulk operation fires the `after` callback exactly ONCE,
   never per-checkbox — so applyFilters() / re-render runs once.

   No dependencies. ES5-safe (no arrow funcs, no template literals).
   ============================================================ */
(function (global) {
  'use strict';

  // ── Internal: find a global function by name (e.g. 'applyFilters') ──
  function _resolveFn(name) {
    if (!name) return null;
    var fn = global[name];
    return (typeof fn === 'function') ? fn : null;
  }

  // ── Set every checkbox in groupSelector to `on`, then run after-callback ONCE
  function bulkSet(groupSelector, on, afterName) {
    var boxes = document.querySelectorAll(groupSelector);
    var changed = false;
    for (var i = 0; i < boxes.length; i++) {
      if (boxes[i].checked !== on) { boxes[i].checked = on; changed = true; }
    }
    if (changed) {
      var fn = _resolveFn(afterName);
      if (fn) fn();
    }
    // Always refresh disabled state regardless of whether anything changed
    refreshGroupState(groupSelector);
  }

  // ── Refresh All/None button disabled state for a single group ──
  function refreshGroupState(groupSelector) {
    var hosts = document.querySelectorAll('[data-bt-group="' + groupSelector + '"]');
    if (!hosts.length) return;
    var boxes = document.querySelectorAll(groupSelector);
    var total = boxes.length;
    var checked = 0;
    for (var i = 0; i < total; i++) if (boxes[i].checked) checked++;
    for (var j = 0; j < hosts.length; j++) {
      var host = hosts[j];
      var allBtn = host.querySelector('.bt-all');
      var noneBtn = host.querySelector('.bt-none');
      var count = host.querySelector('.bt-count');
      if (allBtn)  allBtn.disabled = (checked === total);
      if (noneBtn) noneBtn.disabled = (checked === 0);
      if (count)   count.textContent = checked + '/' + total;
    }
  }

  // ── Refresh all known groups ──
  function refreshAll() {
    var hosts = document.querySelectorAll('[data-bt-group]');
    var seen = {};
    for (var i = 0; i < hosts.length; i++) {
      var sel = hosts[i].getAttribute('data-bt-group');
      if (sel && !seen[sel]) { seen[sel] = 1; refreshGroupState(sel); }
    }
  }

  // ── Inject the All/None buttons into a host element ──
  function _decorate(host) {
    if (host.getAttribute('data-bt-decorated') === '1') return;
    var sel  = host.getAttribute('data-bt-group');
    var after = host.getAttribute('data-bt-after') || '';
    if (!sel) return;
    host.innerHTML =
      '<span class="bt-count" title="checked / total">—</span>' +
      '<button type="button" class="bt-btn bt-all">All</button>' +
      '<button type="button" class="bt-btn bt-none">None</button>';
    host.setAttribute('data-bt-decorated', '1');
    host.querySelector('.bt-all').addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      bulkSet(sel, true, after);
    });
    host.querySelector('.bt-none').addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      bulkSet(sel, false, after);
    });
    // Keep button state in sync as the user clicks individual boxes
    // (delegated mouseup is more robust than change because some dashboards
    //  call applyFilters() on change which can re-render before we listen)
    var groupBoxes = document.querySelectorAll(sel);
    for (var i = 0; i < groupBoxes.length; i++) {
      groupBoxes[i].addEventListener('change', function () { refreshGroupState(sel); });
    }
  }

  function init() {
    var hosts = document.querySelectorAll('[data-bt-group]');
    for (var i = 0; i < hosts.length; i++) _decorate(hosts[i]);
    refreshAll();
  }

  global.BulkToggle = {
    init: init,
    refresh: refreshAll,
    set: function (selector, on, afterName) { bulkSet(selector, !!on, afterName || null); },
  };
})(window);
