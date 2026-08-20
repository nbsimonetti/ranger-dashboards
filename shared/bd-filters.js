/* ============================================================
   Ranger Dashboards — Shared BD filter panel

   Generalised from the TX Physician BD dashboard so every business-development
   dashboard gets the same filtering: multi-select dropdowns with search, per-option
   counts and select-all/clear; single selects; numeric thresholds; text search;
   an active-filter count; and saved presets in localStorage.

   USAGE:
     const F = BDFilters.create({
       mount: '#filters',                 // element or selector
       storageKey: 'dentalBD',            // namespace for saved presets
       rows: () => DASH.providers,        // function returning the full row set
       onChange: rows => renderTable(rows),
       fields: [
         {key:'specialty', label:'Specialty', type:'multi', get:r=>r.specialty},
         {key:'city',      label:'City',      type:'multi', get:r=>r.city},
         {key:'solo',      label:'Solo only', type:'bool',  test:r=>r.solo},
         {key:'minScore',  label:'Min score', type:'min',   get:r=>r.score},
         {key:'q',         label:'Search',    type:'text',  get:r=>r.name+' '+r.city},
       ],
     });
     F.apply();          // re-filter (e.g. after data loads)
     F.filtered()        // current filtered rows

   Field types: multi | select | bool | min | max | text
   'multi' buckets a long tail into "Other (N categories)" so the list stays usable.
   ============================================================ */
(function (global) {
  'use strict';

  var OTHER = '__OTHER__';
  var MAX_OPTS = 60;          // options shown before the tail is bucketed

  function el(sel) { return typeof sel === 'string' ? document.querySelector(sel) : sel; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function debounce(fn, ms) {
    var t; return function () { clearTimeout(t); t = setTimeout(fn, ms); };
  }

  function create(cfg) {
    var mount = el(cfg.mount);
    if (!mount) return null;
    var fields = cfg.fields || [];
    var storeKey = 'rbBDFilters:' + (cfg.storageKey || 'default');
    var state = {};                 // key -> value (array for multi)
    var lastFiltered = [];

    fields.forEach(function (f) { state[f.key] = f.type === 'multi' ? [] : (f.type === 'bool' ? false : ''); });

    /* ---------- option lists (value + count) for multi/select ---------- */
    function optionsFor(f) {
      var counts = {};
      (cfg.rows() || []).forEach(function (r) {
        var v = f.get ? f.get(r) : r[f.key];
        if (v == null || v === '') return;
        counts[v] = (counts[v] || 0) + 1;
      });
      return Object.keys(counts)
        .map(function (k) { return [k, counts[k]]; })
        .sort(function (a, b) { return b[1] - a[1] || String(a[0]).localeCompare(b[0]); });
    }

    /* ---------- markup ---------- */
    mount.classList.add('bdf');
    function fieldHtml(f) {
      if (f.type === 'bool') {
        return '<div class="bdf-f check"><input type="checkbox" id="bdf_' + f.key + '">' +
               '<label for="bdf_' + f.key + '">' + esc(f.label) + '</label></div>';
      }
      var inner;
      if (f.type === 'multi') {
        inner = '<div class="bdf-multi" data-key="' + f.key + '">' +
          '<button type="button" class="bdf-multi-btn"><span class="lab">All</span><span class="arr">&#9660;</span></button>' +
          '<div class="bdf-multi-list"></div></div>';
      } else if (f.type === 'select') {
        inner = '<select id="bdf_' + f.key + '"><option value="">All</option></select>';
      } else if (f.type === 'min' || f.type === 'max') {
        inner = '<input type="number" id="bdf_' + f.key + '" placeholder="' + esc(f.placeholder || '') + '">';
      } else {
        inner = '<input type="text" id="bdf_' + f.key + '" placeholder="' + esc(f.placeholder || 'Search…') + '">';
      }
      return '<div class="bdf-f"><label for="bdf_' + f.key + '">' + esc(f.label) + '</label>' + inner + '</div>';
    }

    mount.innerHTML =
      '<div class="bdf-bar">' +
        '<button type="button" class="bdf-toggle"><span>Filters</span>' +
          '<span class="bdf-pill">0 active</span><span class="bdf-arrow">&#9660;</span></button>' +
        '<span class="bdf-count"></span><span class="bdf-spacer"></span>' +
        '<select class="bdf-presets"><option value="">Saved filters…</option></select>' +
        '<button type="button" class="bdf-btn bdf-load">Load</button>' +
        '<button type="button" class="bdf-btn bdf-save">Save</button>' +
        '<button type="button" class="bdf-btn danger bdf-del">Delete</button>' +
      '</div>' +
      '<div class="bdf-body"><div class="bdf-grid">' + fields.map(fieldHtml).join('') + '</div>' +
        '<div class="bdf-actions"><button type="button" class="bdf-btn primary bdf-apply">Apply</button>' +
        '<button type="button" class="bdf-btn bdf-reset">Reset</button></div></div>';

    var pill = mount.querySelector('.bdf-pill');
    var countEl = mount.querySelector('.bdf-count');
    var presetSel = mount.querySelector('.bdf-presets');

    /* ---------- multi-select rendering ---------- */
    function renderMulti(f) {
      var wrap = mount.querySelector('.bdf-multi[data-key="' + f.key + '"]');
      if (!wrap) return;
      var opts = optionsFor(f);
      var head = opts.slice(0, MAX_OPTS), tail = opts.slice(MAX_OPTS);
      var tailCount = tail.reduce(function (s, o) { return s + o[1]; }, 0);
      wrap._tail = tail.map(function (o) { return o[0]; });

      var list = wrap.querySelector('.bdf-multi-list');
      var html =
        '<input type="text" class="bdf-multi-search" placeholder="Search…">' +
        '<div class="bdf-multi-acts">' +
          '<button type="button" class="all">Select all visible</button>' +
          '<button type="button" class="clr">Clear</button>' +
        '</div>';
      head.forEach(function (o) {
        html += '<label class="bdf-opt"><input type="checkbox" value="' + esc(o[0]) + '">' +
                '<span class="nm">' + esc(o[0]) + '</span><span class="ct">' + o[1].toLocaleString() + '</span></label>';
      });
      if (tail.length) {
        html += '<label class="bdf-opt"><input type="checkbox" value="' + OTHER + '">' +
                '<span class="nm">Other (' + tail.length + ' more)</span>' +
                '<span class="ct">' + tailCount.toLocaleString() + '</span></label>';
      }
      if (!opts.length) html += '<div class="bdf-empty">No values</div>';
      list.innerHTML = html;

      var btn = wrap.querySelector('.bdf-multi-btn');
      btn.onclick = function (e) {
        e.stopPropagation();
        var open = wrap.classList.toggle('open');
        btn.classList.toggle('on', open);
        document.querySelectorAll('.bdf-multi.open').forEach(function (o) {
          if (o !== wrap) { o.classList.remove('open'); o.querySelector('.bdf-multi-btn').classList.remove('on'); }
        });
      };
      list.onclick = function (e) { e.stopPropagation(); };
      list.querySelector('.bdf-multi-search').oninput = function () {
        var q = this.value.toLowerCase();
        list.querySelectorAll('.bdf-opt').forEach(function (o) {
          o.style.display = o.querySelector('.nm').textContent.toLowerCase().indexOf(q) >= 0 ? '' : 'none';
        });
      };
      list.querySelector('.all').onclick = function () {
        list.querySelectorAll('.bdf-opt').forEach(function (o) {
          if (o.style.display !== 'none') o.querySelector('input').checked = true;
        });
        syncMulti(f); apply();
      };
      list.querySelector('.clr').onclick = function () {
        list.querySelectorAll('input[type=checkbox]').forEach(function (c) { c.checked = false; });
        syncMulti(f); apply();
      };
      list.querySelectorAll('input[type=checkbox]').forEach(function (c) {
        c.onchange = function () { syncMulti(f); apply(); };
      });
      syncMulti(f, true);
    }

    function syncMulti(f, quiet) {
      var wrap = mount.querySelector('.bdf-multi[data-key="' + f.key + '"]');
      var checked = Array.prototype.map.call(
        wrap.querySelectorAll('input[type=checkbox]:checked'), function (c) { return c.value; });
      state[f.key] = checked;
      var lab = wrap.querySelector('.lab');
      lab.textContent = !checked.length ? 'All'
        : (checked.length === 1 ? (checked[0] === OTHER ? 'Other' : checked[0]) : checked.length + ' selected');
      if (!quiet) updatePill();
    }

    /* ---------- wire simple fields ---------- */
    fields.forEach(function (f) {
      if (f.type === 'multi') { renderMulti(f); return; }
      var input = mount.querySelector('#bdf_' + f.key);
      if (!input) return;
      if (f.type === 'select') {
        var opts = f.options || optionsFor(f).map(function (o) { return [o[0], o[0] + ' (' + o[1].toLocaleString() + ')']; });
        opts.forEach(function (o) {
          var v = Array.isArray(o) ? o[0] : o, t = Array.isArray(o) ? o[1] : o;
          input.insertAdjacentHTML('beforeend', '<option value="' + esc(v) + '">' + esc(t) + '</option>');
        });
      }
      var handler = function () {
        state[f.key] = f.type === 'bool' ? input.checked : input.value;
        apply();
      };
      if (f.type === 'text' || f.type === 'min' || f.type === 'max') input.oninput = debounce(handler, 220);
      else input.onchange = handler;
    });

    document.addEventListener('click', function () {
      document.querySelectorAll('.bdf-multi.open').forEach(function (o) {
        o.classList.remove('open'); o.querySelector('.bdf-multi-btn').classList.remove('on');
      });
    });

    /* ---------- filtering ---------- */
    function activeCount() {
      var n = 0;
      fields.forEach(function (f) {
        var v = state[f.key];
        if (f.type === 'multi') { if (v && v.length) n++; }
        else if (f.type === 'bool') { if (v) n++; }
        else if (v !== '' && v != null) n++;
      });
      return n;
    }

    function matches(r) {
      for (var i = 0; i < fields.length; i++) {
        var f = fields[i], v = state[f.key];
        if (f.type === 'multi') {
          if (!v || !v.length) continue;
          var wrap = mount.querySelector('.bdf-multi[data-key="' + f.key + '"]');
          var val = f.get ? f.get(r) : r[f.key];
          var ok = v.indexOf(String(val)) >= 0;
          if (!ok && v.indexOf(OTHER) >= 0 && wrap._tail) ok = wrap._tail.indexOf(String(val)) >= 0;
          if (!ok) return false;
        } else if (f.type === 'bool') {
          if (v && !(f.test ? f.test(r) : r[f.key])) return false;
        } else if (f.type === 'select') {
          if (v === '') continue;
          if (f.test) { if (!f.test(r, v)) return false; }
          else if (String(f.get ? f.get(r) : r[f.key]) !== v) return false;
        } else if (f.type === 'min' || f.type === 'max') {
          if (v === '' || v == null) continue;
          var num = f.get ? f.get(r) : r[f.key];
          if (num == null || isNaN(num)) return false;
          if (f.type === 'min' && +num < +v) return false;
          if (f.type === 'max' && +num > +v) return false;
        } else {
          if (!v) continue;
          var hay = String(f.get ? f.get(r) : r[f.key] || '').toLowerCase();
          if (hay.indexOf(String(v).toLowerCase()) < 0) return false;
        }
      }
      return true;
    }

    function updatePill() {
      var n = activeCount();
      pill.textContent = n ? n + ' active' : '0 active';
      pill.classList.toggle('on', n > 0);
    }

    function apply() {
      var all = cfg.rows() || [];
      lastFiltered = all.filter(matches);
      updatePill();
      countEl.innerHTML = '<b>' + lastFiltered.length.toLocaleString() + '</b> of ' +
        all.length.toLocaleString() + (cfg.noun ? ' ' + cfg.noun : '');
      if (cfg.onChange) cfg.onChange(lastFiltered);
    }

    function reset() {
      fields.forEach(function (f) {
        if (f.type === 'multi') {
          var wrap = mount.querySelector('.bdf-multi[data-key="' + f.key + '"]');
          wrap.querySelectorAll('input[type=checkbox]').forEach(function (c) { c.checked = false; });
          syncMulti(f, true);
        } else {
          var input = mount.querySelector('#bdf_' + f.key);
          if (!input) return;
          if (f.type === 'bool') { input.checked = false; state[f.key] = false; }
          else { input.value = ''; state[f.key] = ''; }
        }
      });
      apply();
    }

    /* ---------- saved presets ---------- */
    function getPresets() {
      try { return JSON.parse(localStorage.getItem(storeKey) || '{}'); } catch (e) { return {}; }
    }
    function setPresets(o) { try { localStorage.setItem(storeKey, JSON.stringify(o)); } catch (e) {} }
    function fillPresets() {
      presetSel.querySelectorAll('option:not(:first-child)').forEach(function (o) { o.remove(); });
      Object.keys(getPresets()).sort().forEach(function (n) {
        presetSel.insertAdjacentHTML('beforeend', '<option value="' + esc(n) + '">' + esc(n) + '</option>');
      });
    }
    mount.querySelector('.bdf-save').onclick = function () {
      var name = prompt('Name this filter preset:');
      if (!name) return;
      var p = getPresets(); p[name] = JSON.parse(JSON.stringify(state)); setPresets(p);
      fillPresets(); presetSel.value = name;
    };
    mount.querySelector('.bdf-load').onclick = function () {
      var name = presetSel.value; if (!name) return;
      var vals = getPresets()[name]; if (!vals) return;
      fields.forEach(function (f) {
        var v = vals[f.key];
        if (f.type === 'multi') {
          var wrap = mount.querySelector('.bdf-multi[data-key="' + f.key + '"]');
          wrap.querySelectorAll('input[type=checkbox]').forEach(function (c) {
            c.checked = Array.isArray(v) && v.indexOf(c.value) >= 0;
          });
          syncMulti(f, true);
        } else {
          var input = mount.querySelector('#bdf_' + f.key);
          if (!input) return;
          if (f.type === 'bool') { input.checked = !!v; state[f.key] = !!v; }
          else { input.value = v || ''; state[f.key] = v || ''; }
        }
      });
      apply();
    };
    mount.querySelector('.bdf-del').onclick = function () {
      var name = presetSel.value; if (!name) return;
      if (!confirm('Delete preset "' + name + '"?')) return;
      var p = getPresets(); delete p[name]; setPresets(p); fillPresets();
    };
    mount.querySelector('.bdf-apply').onclick = apply;
    mount.querySelector('.bdf-reset').onclick = reset;
    mount.querySelector('.bdf-toggle').onclick = function () { mount.classList.toggle('open'); };
    if (cfg.startOpen) mount.classList.add('open');
    fillPresets();
    apply();

    return {
      apply: apply,
      reset: reset,
      filtered: function () { return lastFiltered; },
      state: state,
      /* rebuild option lists after the data changes */
      refresh: function () { fields.forEach(function (f) { if (f.type === 'multi') renderMulti(f); }); apply(); },
    };
  }

  global.BDFilters = { create: create };
})(window);
