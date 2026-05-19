/* ============================================================
   Ranger Dashboards — Shared Score Hover Tooltip Module

   Provides a uniform hover tooltip for every score badge across
   all dashboards. Attach to any element via data attributes or
   the JS API.

   USAGE:

   A) Data-attribute pattern (recommended for table rows rendered
      via template strings):

      <span class="shv-trigger"
            data-shv-title="Composite Score"
            data-shv-total="73.8"
            data-shv-max="100"
            data-shv-theme="dark"
            data-shv-components='[
              {"label":"Quant","value":76.7,"max":100,"color":"#3182ce"},
              {"label":"Deal Econ","value":67.9,"max":100,"color":"#c8a951"},
              {"label":"Qualitative","value":74.0,"max":100,"color":"#38a169"}
            ]'
            data-shv-foot="Click for full breakdown">42</span>

      Then call ScoreHover.init() once on page load to attach the
      global mouseover/focus listeners. Newly-added elements will
      be picked up automatically (uses event delegation).

   B) Programmatic API (if templating is awkward):

      ScoreHover.attach(element, {
        title: 'Composite Score',
        total: 73.8,
        max: 100,
        theme: 'dark',
        components: [...],
        subgroups: [ { groupLabel: '...', components: [...] } ],
        foot: 'Methodology link...'
      });
   ============================================================ */

(function (global) {
  'use strict';

  let tipEl = null;
  let hideTimer = null;
  let showTimer = null;

  // Embedded element data cache for programmatic attach()
  const cache = new WeakMap();

  function ensureTipEl() {
    if (tipEl) return tipEl;
    tipEl = document.createElement('div');
    tipEl.className = 'shv-tip';
    document.body.appendChild(tipEl);
    // Keep tooltip alive when hovering it (so subgroup links can be clicked)
    tipEl.addEventListener('mouseenter', () => clearTimeout(hideTimer));
    tipEl.addEventListener('mouseleave', () => hide());
    return tipEl;
  }

  function fmtNum(v, dec) {
    if (v == null || isNaN(v)) return '—';
    return Number(v).toLocaleString('en-US', {
      minimumFractionDigits: dec != null ? dec : 0,
      maximumFractionDigits: dec != null ? dec : 1,
    });
  }

  function colorForPct(pct) {
    if (pct >= 70) return '#38a169';
    if (pct >= 40) return '#dd6b20';
    return '#e53e3e';
  }

  function renderComponents(components) {
    if (!components || !components.length) return '';
    return components.map(c => {
      const v = c.value;
      const max = c.max != null ? c.max : 100;
      const pct = max > 0 ? Math.max(0, Math.min(100, (v / max) * 100)) : 0;
      const color = c.color || colorForPct(pct);
      const valTxt = c.fmt
        ? c.fmt
        : (c.maxLabel === false
            ? fmtNum(v, c.dec != null ? c.dec : 1)
            : `${fmtNum(v, c.dec != null ? c.dec : 1)} / ${fmtNum(max, 0)}`);
      return `
        <div class="shv-comp-row">
          <div class="shv-comp-line">
            <span class="shv-comp-label">${escapeHtml(c.label)}</span>
            <span class="shv-comp-val">${escapeHtml(valTxt)}</span>
          </div>
          <div class="shv-comp-bar"><div class="shv-comp-fill" style="width:${pct}%;background:${color}"></div></div>
        </div>`;
    }).join('');
  }

  function renderTooltipHTML(data) {
    const totalStr = data.total != null
      ? `${fmtNum(data.total, 1)}${data.max != null ? ' / ' + fmtNum(data.max, 0) : ''}`
      : '';
    let html = '';
    if (data.title || data.total != null) {
      html += `<div class="shv-tip-title">
        <span>${escapeHtml(data.title || '')}</span>
        ${totalStr ? `<span class="shv-tip-total">${totalStr}</span>` : ''}
      </div>`;
    }
    if (data.components && data.components.length) {
      html += renderComponents(data.components);
    }
    if (data.subgroups && data.subgroups.length) {
      data.subgroups.forEach(sg => {
        html += `<div class="shv-tip-section-h">${escapeHtml(sg.groupLabel)}</div>`;
        html += renderComponents(sg.components);
      });
    }
    if (data.foot) {
      html += `<div class="shv-tip-foot">${escapeHtml(data.foot)}</div>`;
    }
    return html;
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
    );
  }

  function positionTip(target) {
    const tip = ensureTipEl();
    const r = target.getBoundingClientRect();
    const tipW = tip.offsetWidth || 260;
    const tipH = tip.offsetHeight || 200;
    const vw = window.innerWidth, vh = window.innerHeight;
    const pad = 8;

    // Prefer below, fall back to above
    let top = r.bottom + 6;
    if (top + tipH > vh - pad) {
      top = r.top - tipH - 6;
    }
    if (top < pad) top = pad;

    // Prefer left-aligned with target
    let left = r.left;
    if (left + tipW > vw - pad) {
      left = vw - tipW - pad;
    }
    if (left < pad) left = pad;

    tip.style.top = top + 'px';
    tip.style.left = left + 'px';
  }

  function show(target, data) {
    clearTimeout(showTimer);
    clearTimeout(hideTimer);
    showTimer = setTimeout(() => {
      const tip = ensureTipEl();
      tip.innerHTML = renderTooltipHTML(data);
      tip.classList.toggle('shv-light', data.theme === 'light');
      // Show (needs layout to measure size before positioning)
      tip.style.opacity = '0';
      tip.style.display = 'block';
      requestAnimationFrame(() => {
        positionTip(target);
        tip.classList.add('shv-show');
      });
    }, 130);
  }

  function hide() {
    clearTimeout(showTimer);
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      if (tipEl) tipEl.classList.remove('shv-show');
    }, 100);
  }

  function getDataFromElement(el) {
    // Check programmatic cache first
    if (cache.has(el)) return cache.get(el);
    // Read from data-shv-* attributes
    const data = {
      title: el.dataset.shvTitle,
      total: el.dataset.shvTotal != null ? parseFloat(el.dataset.shvTotal) : null,
      max: el.dataset.shvMax != null ? parseFloat(el.dataset.shvMax) : null,
      theme: el.dataset.shvTheme,
      foot: el.dataset.shvFoot,
    };
    try { if (el.dataset.shvComponents) data.components = JSON.parse(el.dataset.shvComponents); } catch (e) {}
    try { if (el.dataset.shvSubgroups) data.subgroups = JSON.parse(el.dataset.shvSubgroups); } catch (e) {}
    return data;
  }

  // ----- Public API -----
  const SH = {
    init: function (opts) {
      ensureTipEl();
      const triggerSelector = (opts && opts.triggerSelector) || '.shv-trigger';
      document.addEventListener('mouseover', e => {
        const t = e.target.closest(triggerSelector);
        if (!t) return;
        const data = getDataFromElement(t);
        if (!data || (!data.components && !data.subgroups && !data.total)) return;
        show(t, data);
      });
      document.addEventListener('mouseout', e => {
        const t = e.target.closest(triggerSelector);
        if (!t) return;
        // Only hide if leaving to non-tooltip element
        if (e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest('.shv-tip')) return;
        hide();
      });
      // Keyboard accessibility
      document.addEventListener('focusin', e => {
        const t = e.target.closest && e.target.closest(triggerSelector);
        if (!t) return;
        const data = getDataFromElement(t);
        if (data) show(t, data);
      });
      document.addEventListener('focusout', e => {
        const t = e.target.closest && e.target.closest(triggerSelector);
        if (t) hide();
      });
      // Scroll → hide (positions become stale)
      let scrollT;
      document.addEventListener('scroll', () => {
        clearTimeout(scrollT);
        scrollT = setTimeout(() => hide(), 50);
      }, true);
    },

    attach: function (el, data) {
      if (!el) return;
      el.classList.add('shv-trigger');
      el.setAttribute('tabindex', '0');
      cache.set(el, data);
    },

    // Stringify a JS object to be safe as a data-shv-components attribute value
    encode: function (obj) {
      return escapeHtml(JSON.stringify(obj)).replace(/&quot;/g, '&#34;');
    },
  };

  global.ScoreHover = SH;
})(window);
