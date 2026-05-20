/* ============================================================
   Ranger Dashboards — Shared Column Picker

   Lets users show/hide columns in a table. Persists choice in
   localStorage per dashboard. Also exposes a setter to query
   visibility for use by the table render code.

   USAGE:
     const picker = ColumnPicker.create({
       dashboardId: 'ma',
       title: 'Choose Columns',
       theme: 'dark',
       triggerMount: '#cp-trigger-mount',
       columns: [
         { key: 'rank',  label: 'Rank',  defaultShown: true, locked: true },
         { key: 'NAME',  label: 'Bank',  defaultShown: true, locked: true },
         { key: 'TBVE',  label: 'TBVE',  defaultShown: true },
         { key: 'roa',   label: 'ROA %', defaultShown: false },
         ...
       ],
       onChange: () => { rerender(); }
     });

     picker.isVisible('roa');     // → false
     picker.visibleKeys();        // → ['rank','NAME','TBVE',...]
   ============================================================ */
(function (global) {
  'use strict';

  const $ = (s, p) => (p || document).querySelector(s);

  function lsKey(id) { return `rangerCols:${id}`; }
  function safeGet(k) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : null; } catch (e) { return null; } }
  function safeSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }

  function create(opts) {
    const cols = (opts.columns || []).map(c => Object.assign({ defaultShown: true }, c));
    const stored = safeGet(lsKey(opts.dashboardId)) || {};

    // Initialize visibility state
    const state = {};
    cols.forEach(c => {
      if (c.locked) state[c.key] = true;
      else if (stored[c.key] != null) state[c.key] = !!stored[c.key];
      else state[c.key] = c.defaultShown;
    });

    function isModified() {
      return cols.some(c => !c.locked && state[c.key] !== c.defaultShown);
    }
    function visibleKeys() {
      return cols.filter(c => state[c.key]).map(c => c.key);
    }
    function isVisible(key) {
      return !!state[key];
    }
    function persistAndNotify() {
      const toStore = {};
      cols.forEach(c => { if (!c.locked) toStore[c.key] = state[c.key]; });
      safeSet(lsKey(opts.dashboardId), toStore);
      updateTriggerState();
      if (typeof opts.onChange === 'function') opts.onChange();
    }

    function mountTrigger() {
      const m = typeof opts.triggerMount === 'string' ? $(opts.triggerMount) : opts.triggerMount;
      if (!m) return;
      const b = document.createElement('button');
      b.id = 'cp-trigger-' + opts.dashboardId;
      b.className = 'cp-trigger';
      b.type = 'button';
      b.innerHTML = '<span>☰</span> <span class="cp-trigger-label">Columns</span>';
      b.onclick = openPanel;
      m.appendChild(b);
    }

    function updateTriggerState() {
      const t = $('#cp-trigger-' + opts.dashboardId);
      if (!t) return;
      const label = t.querySelector('.cp-trigger-label');
      const count = cols.filter(c => state[c.key]).length;
      const total = cols.length;
      if (label) label.textContent = `Columns (${count}/${total})`;
      t.classList.toggle('cp-modified', isModified());
    }

    function openPanel() {
      let panel = $('#cp-panel-' + opts.dashboardId);
      let backdrop = $('#cp-backdrop-' + opts.dashboardId);
      if (!panel) {
        backdrop = document.createElement('div');
        backdrop.id = 'cp-backdrop-' + opts.dashboardId;
        backdrop.className = 'cp-backdrop';
        backdrop.onclick = closePanel;
        panel = document.createElement('div');
        panel.id = 'cp-panel-' + opts.dashboardId;
        panel.className = 'cp-panel' + (opts.theme === 'dark' ? ' cp-dark' : '');
        document.body.appendChild(backdrop);
        document.body.appendChild(panel);
      }
      rerenderPanel(panel);
      // Force reflow before adding open class for transition
      requestAnimationFrame(() => {
        panel.classList.add('cp-open');
        backdrop.classList.add('cp-open');
      });
    }

    function closePanel() {
      const panel = $('#cp-panel-' + opts.dashboardId);
      const backdrop = $('#cp-backdrop-' + opts.dashboardId);
      if (panel) panel.classList.remove('cp-open');
      if (backdrop) backdrop.classList.remove('cp-open');
    }

    function rerenderPanel(panel) {
      panel.innerHTML = `
        <div class="cp-head">
          <div class="cp-title">${opts.title || 'Choose Columns'}</div>
          <button type="button" class="cp-close" aria-label="Close">×</button>
        </div>
        <div class="cp-actions">
          <button type="button" data-act="all">Show All</button>
          <button type="button" data-act="default">Reset to Default</button>
          <button type="button" data-act="essential">Essential Only</button>
        </div>
        <div class="cp-list">
          ${cols.map(c => `
            <label>
              <input type="checkbox" data-key="${c.key}" ${state[c.key] ? 'checked' : ''} ${c.locked ? 'disabled' : ''}>
              <span>${c.label}${c.locked ? ' <span class="cp-list-locked">(always shown)</span>' : ''}</span>
            </label>
          `).join('')}
        </div>
        <div class="cp-foot">Choices saved to this browser. ${cols.length} total columns.</div>
      `;
      panel.querySelector('.cp-close').onclick = closePanel;
      panel.querySelector('[data-act="all"]').onclick = () => {
        cols.forEach(c => { state[c.key] = true; });
        rerenderPanel(panel);
        persistAndNotify();
      };
      panel.querySelector('[data-act="default"]').onclick = () => {
        cols.forEach(c => { state[c.key] = c.locked ? true : c.defaultShown; });
        rerenderPanel(panel);
        persistAndNotify();
      };
      panel.querySelector('[data-act="essential"]').onclick = () => {
        cols.forEach(c => { state[c.key] = !!c.essential || c.locked; });
        rerenderPanel(panel);
        persistAndNotify();
      };
      panel.querySelectorAll('input[type=checkbox]').forEach(cb => {
        cb.addEventListener('change', () => {
          state[cb.dataset.key] = cb.checked;
          persistAndNotify();
        });
      });
    }

    mountTrigger();
    updateTriggerState();

    return {
      isVisible,
      visibleKeys,
      open: openPanel,
      close: closePanel,
    };
  }

  global.ColumnPicker = { create };
})(window);
