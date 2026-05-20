/* ============================================================
   Ranger Dashboards — Shared Sortable Table

   Drop-in client-side sort for any <table> with a <thead> and a
   <tbody>. Opt-OUT model: every table on the page is wired up
   automatically unless it (or a specific <th>) is opted out.

   WHEN A TABLE IS SKIPPED (no double-handlers, no conflicts):
     - <table data-no-sort>                       (whole table opted out)
     - <table class="no-sort">                    (whole table opted out)
     - <th> with data-tbl  attribute              (Deposit pattern — already sorted)
     - <th> with data-key  attribute              (M&A pattern — already sorted)
     - <th> with data-col  attribute              (Deposit per-col attribute)
     - <th> with onclick attribute                (legacy inline handler)
     - <th data-no-sort>                          (per-header opt-out)
     - Layout tables: no <thead> OR no <tbody>    (auto-skipped)

   CELL VALUE COERCION:
     1. <td data-sort> attribute wins — use it as the sort key.
     2. Otherwise: strip $, commas, %, then parseFloat.
     3. If all visible cells in the column parse as numeric, treat
        the column as numeric (descending on first click).
     4. Else: lowercased text compare (ascending on first click).

   USAGE:
     <script src="../shared/sortable-table.js"></script>
     <link  rel="stylesheet" href="../shared/sortable-table.css"/>
     // Auto-attaches on DOMContentLoaded.

     // After a dynamic re-render that replaces tbody innerHTML, call:
     SortableTable.refresh();
     // (Also: SortableTable.refresh(specificTableElement);)

   The visual cues (▲ / ▼) are added via existing .sort-asc /
   .sort-desc classes — the dashboards already style them.
   ============================================================ */
(function (global) {
  'use strict';

  function isOptedOut(table) {
    if (!table) return true;
    if (table.hasAttribute('data-no-sort')) return true;
    if (table.classList.contains('no-sort')) return true;
    return false;
  }
  function isHeaderOptedOut(th) {
    if (!th) return true;
    if (th.hasAttribute('data-no-sort')) return true;
    if (th.hasAttribute('data-tbl')) return true;     // Deposit existing-sort marker
    if (th.hasAttribute('data-key')) return true;     // M&A existing-sort marker
    if (th.hasAttribute('data-col')) return true;     // Deposit per-col marker
    if (th.hasAttribute('onclick')) return true;      // Legacy inline handler
    return false;
  }

  function getCellSortKey(td) {
    if (!td) return '';
    if (td.hasAttribute('data-sort')) return td.getAttribute('data-sort');
    // Strip currency, commas, percent, whitespace
    var raw = (td.textContent || '').trim();
    return raw;
  }
  function toNum(s) {
    if (s == null) return NaN;
    if (typeof s === 'number') return s;
    s = String(s).replace(/[\$,%\s]/g, '');
    // Handle "1.2M", "350K", "2.5B"
    var m = /^(-?\d+(?:\.\d+)?)([KkMmBb])$/.exec(s);
    if (m) {
      var mult = m[2].toUpperCase() === 'K' ? 1e3 : m[2].toUpperCase() === 'M' ? 1e6 : 1e9;
      return parseFloat(m[1]) * mult;
    }
    var n = parseFloat(s);
    return isNaN(n) ? NaN : n;
  }
  function columnIsNumeric(rows, colIdx) {
    var nonEmpty = 0, numeric = 0;
    for (var i = 0; i < rows.length && nonEmpty < 8; i++) {
      var td = rows[i].cells[colIdx];
      if (!td) continue;
      var v = getCellSortKey(td);
      if (!v || v === '—' || v === '-' || v === 'N/A') continue;
      nonEmpty++;
      if (!isNaN(toNum(v))) numeric++;
    }
    return nonEmpty > 0 && (numeric / nonEmpty) >= 0.6;
  }

  function sortRows(tbody, colIdx, asc, isNumeric) {
    var rows = Array.prototype.slice.call(tbody.rows);
    rows.sort(function (a, b) {
      var va = getCellSortKey(a.cells[colIdx]);
      var vb = getCellSortKey(b.cells[colIdx]);
      var emptyA = !va || va === '—' || va === '-' || va === 'N/A';
      var emptyB = !vb || vb === '—' || vb === '-' || vb === 'N/A';
      if (emptyA && emptyB) return 0;
      if (emptyA) return 1;   // empties always last regardless of asc/desc
      if (emptyB) return -1;
      if (isNumeric) {
        var na = toNum(va), nb = toNum(vb);
        if (isNaN(na) && isNaN(nb)) return 0;
        if (isNaN(na)) return 1;
        if (isNaN(nb)) return -1;
        return asc ? (na - nb) : (nb - na);
      }
      var sa = va.toLowerCase(), sb = vb.toLowerCase();
      if (sa < sb) return asc ? -1 : 1;
      if (sa > sb) return asc ? 1 : -1;
      return 0;
    });
    // Re-append in sorted order
    var frag = document.createDocumentFragment();
    for (var i = 0; i < rows.length; i++) frag.appendChild(rows[i]);
    tbody.appendChild(frag);
  }

  function clearOtherSortMarks(thead, except) {
    var ths = thead.querySelectorAll('th');
    for (var i = 0; i < ths.length; i++) {
      if (ths[i] !== except) ths[i].classList.remove('sort-asc', 'sort-desc');
    }
  }

  function decorateTable(table) {
    if (isOptedOut(table)) return;
    var thead = table.tHead;
    var tbody = table.tBodies && table.tBodies[0];
    if (!thead || !tbody) return;   // layout table — skip
    var ths = thead.rows.length ? thead.rows[thead.rows.length - 1].cells : [];
    if (!ths.length) return;
    for (var i = 0; i < ths.length; i++) {
      var th = ths[i];
      if (isHeaderOptedOut(th)) continue;
      // Skip headers we've already wired — but track per-<th> via a custom
      // property, NOT per-<table>. Dashboards that rebuild headers (e.g. M&A's
      // visibleCols-driven rankHead) get fresh <th> elements and need re-decoration.
      if (th.__sortableAttached) continue;
      th.__sortableAttached = true;
      // Use a closure to capture column index
      (function (colIdx, headerEl) {
        headerEl.classList.add('sortable-th');
        headerEl.addEventListener('click', function (e) {
          // Don't fire if click landed on a resize handle (last 10px)
          var r = headerEl.getBoundingClientRect();
          if (e.clientX > r.right - 10 && headerEl.hasAttribute('data-rc-key')) return;
          var tbody2 = table.tBodies && table.tBodies[0];
          if (!tbody2) return;
          var rows = Array.prototype.slice.call(tbody2.rows);
          if (!rows.length) return;
          var isNum = columnIsNumeric(rows, colIdx);
          var wasAsc = headerEl.classList.contains('sort-asc');
          var wasDesc = headerEl.classList.contains('sort-desc');
          // Default direction on first click: numeric → desc, text → asc
          var asc;
          if (wasAsc) asc = false;
          else if (wasDesc) asc = true;
          else asc = !isNum;
          clearOtherSortMarks(thead, headerEl);
          headerEl.classList.remove('sort-asc', 'sort-desc');
          headerEl.classList.add(asc ? 'sort-asc' : 'sort-desc');
          sortRows(tbody2, colIdx, asc, isNum);
        });
      })(i, th);
    }
  }

  function refresh(scope) {
    var root = (scope instanceof Element) ? scope : document;
    if (root.tagName === 'TABLE') { decorateTable(root); return; }
    var tables = root.getElementsByTagName('table');
    for (var i = 0; i < tables.length; i++) decorateTable(tables[i]);
  }

  function init() { refresh(document); }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // MutationObserver auto-rewires sort handlers after dynamic tbody/innerHTML
  // replaces (no per-dashboard refresh() calls needed). Debounced via rAF so a
  // burst of mutations from one re-render becomes a single decorate pass.
  var _scheduled = false;
  function scheduleRefresh() {
    if (_scheduled) return;
    _scheduled = true;
    var run = function () { _scheduled = false; refresh(document); };
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(run);
    else setTimeout(run, 16);
  }
  if (typeof MutationObserver === 'function') {
    var mo = new MutationObserver(function (records) {
      for (var i = 0; i < records.length; i++) {
        var added = records[i].addedNodes;
        if (!added || !added.length) continue;
        for (var j = 0; j < added.length; j++) {
          var node = added[j];
          if (node.nodeType !== 1) continue; // ELEMENT_NODE
          // Cheap check: did we add (or are we inside) a <table>?
          if (node.tagName === 'TABLE' ||
              node.tagName === 'TBODY' ||
              node.tagName === 'THEAD' ||
              (node.getElementsByTagName && node.getElementsByTagName('table').length)) {
            scheduleRefresh();
            return;
          }
        }
      }
    });
    // Wait until body exists before observing
    var startObserve = function () {
      if (document.body) mo.observe(document.body, { childList: true, subtree: true });
    };
    if (document.body) startObserve();
    else document.addEventListener('DOMContentLoaded', startObserve);
  }

  global.SortableTable = { init: init, refresh: refresh };
})(window);
