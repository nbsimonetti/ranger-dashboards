/* ============================================================
   Ranger Dashboards — Shared Active-Filter Chip Strip

   USAGE:
     const strip = FilterChips.create({
       mount: document.getElementById('chipStripMount'),
       getChips: () => {
         // Return array of chips reflecting the CURRENT filter state.
         // Each chip: { key, label, value, onRemove }
         return [
           { key: 'region', label: 'Region', value: 'East TX',
             onRemove: () => { S.filters.region = ''; applyFilters(); strip.refresh(); } },
           ...
         ];
       },
       onClearAll: () => { resetAllFilters(); strip.refresh(); }
     });

     // After any filter UI change:
     strip.refresh();

   The strip is hidden when no chips are active.
   ============================================================ */
(function (global) {
  'use strict';

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function create(opts) {
    const mount = opts.mount;
    if (!mount) return null;
    mount.classList.add('fc-strip');

    function refresh() {
      const chips = (opts.getChips ? opts.getChips() : []) || [];
      if (!chips.length) { mount.innerHTML = ''; return; }
      let html = '<span class="fc-strip-label">Filters:</span>';
      chips.forEach((c, i) => {
        const v = c.value != null ? c.value : '';
        const lbl = c.label ? c.label + ':' : '';
        html += `<span class="fc-chip" data-i="${i}" title="${escapeHtml(c.tooltip || '')}">`+
          (lbl ? `<span class="fc-chip-key">${escapeHtml(lbl)}</span>` : '')+
          `<span class="fc-chip-val">${escapeHtml(v)}</span>`+
          `<button type="button" class="fc-chip-x" aria-label="Remove filter">×</button>`+
          `</span>`;
      });
      html += `<button type="button" class="fc-clear-all">Clear all</button>`;
      mount.innerHTML = html;
      // Wire remove handlers
      mount.querySelectorAll('.fc-chip').forEach(el => {
        const i = parseInt(el.dataset.i, 10);
        const chip = chips[i];
        const x = el.querySelector('.fc-chip-x');
        if (x && chip && typeof chip.onRemove === 'function') {
          x.addEventListener('click', () => { chip.onRemove(); refresh(); });
        }
      });
      const clear = mount.querySelector('.fc-clear-all');
      if (clear && typeof opts.onClearAll === 'function') {
        clear.addEventListener('click', () => { opts.onClearAll(); refresh(); });
      }
    }

    refresh();
    return { refresh };
  }

  global.FilterChips = { create };
})(window);
