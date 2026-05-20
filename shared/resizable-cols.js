/* ============================================================
   Ranger Dashboards — Shared Resizable Column Headers

   USAGE:
     // Add class="resizable-cols" to your <table>
     // Add data-rc-key="<key>" to each <th> you want resizable
     ResizableCols.attach({
       table: document.querySelector('table.resizable-cols'),
       dashboardId: 'ma',
       tableId: 'rankings'
     });

   Widths persist per dashboard+table+columnKey in localStorage.
   Call ResizableCols.applyAll() after re-rendering headers to
   restore widths.
   ============================================================ */
(function (global) {
  'use strict';

  function lsKey(dashId, tableId) { return `rangerColWidths:${dashId}:${tableId}`; }
  function safeGet(k) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : {}; } catch (e) { return {}; } }
  function safeSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }

  const registry = [];

  function applyStored(table, dashId, tableId) {
    const widths = safeGet(lsKey(dashId, tableId));
    table.querySelectorAll('th[data-rc-key]').forEach(th => {
      const k = th.dataset.rcKey;
      const w = widths[k];
      if (w) th.style.width = w + 'px';
    });
  }

  function attach(opts) {
    const table = opts.table;
    if (!table) return;
    const dashId = opts.dashboardId;
    const tableId = opts.tableId || 'default';
    table.classList.add('resizable-cols');
    applyStored(table, dashId, tableId);
    registry.push({ table, dashId, tableId });

    let startX = 0, startWidth = 0, targetTh = null;
    function onDown(e) {
      const th = e.target.closest('th[data-rc-key]');
      if (!th) return;
      // Only fire on the resize handle area (right 8px)
      const r = th.getBoundingClientRect();
      if (e.clientX < r.right - 10) return;
      e.preventDefault();
      startX = e.clientX;
      startWidth = th.offsetWidth;
      targetTh = th;
      th.classList.add('rc-resizing');
      table.classList.add('rc-dragging');
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    }
    function onMove(e) {
      if (!targetTh) return;
      const delta = e.clientX - startX;
      let newW = Math.max(40, startWidth + delta);
      targetTh.style.width = newW + 'px';
    }
    function onUp() {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      if (targetTh) {
        const widths = safeGet(lsKey(dashId, tableId));
        widths[targetTh.dataset.rcKey] = targetTh.offsetWidth;
        safeSet(lsKey(dashId, tableId), widths);
        targetTh.classList.remove('rc-resizing');
      }
      table.classList.remove('rc-dragging');
      targetTh = null;
    }

    table.addEventListener('mousedown', onDown);
  }

  function applyAll() {
    registry.forEach(({ table, dashId, tableId }) => applyStored(table, dashId, tableId));
  }

  function reset(dashId, tableId) {
    try { localStorage.removeItem(lsKey(dashId, tableId)); } catch (e) {}
  }

  global.ResizableCols = { attach, applyAll, reset };
})(window);
