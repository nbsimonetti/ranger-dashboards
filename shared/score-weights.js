/* ============================================================
   Ranger Dashboards — Shared Score Weights Module
   Provides a drawer UI for adjusting scoring weights at runtime.

   Usage:
     ScoreWeights.init({
       dashboardId: 'ma',
       theme: 'dark',         // 'light' or 'dark'
       triggerSelector: '#sw-trigger-mount',
       bannerSelector:  '#sw-banner-mount',
       scoringSystems: [
         {
           id: 'composite',
           label: 'Composite Top-Level',
           tabLabel: 'Composite',
           components: [
             { key: 'quant',    label: 'Quant', default: 50, min: 0, max: 100, step: 1 },
             { key: 'dealEcon', label: 'Deal Economics', default: 25, min: 0, max: 100, step: 1 },
             { key: 'qual',     label: 'Qualitative', default: 25, min: 0, max: 100, step: 1 },
           ],
           normalizeTo: 100,        // optional
         },
       ],
       onChange: (allWeights) => { ... },  // called whenever weights change
     });

   The onChange callback receives an object like:
     { composite: {quant: 50, dealEcon: 25, qual: 25}, quant: {...}, ... }
   ============================================================ */

(function (global) {
  'use strict';

  // Polyfill for older browsers
  const debounce = (fn, ms) => {
    let t;
    return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  };

  const $ = (s, p = document) => p.querySelector(s);

  // localStorage helpers
  const lsKey = (dashId, scoringId) => `rangerWeights:${dashId}:${scoringId}`;
  const lsPresetKey = (dashId) => `rangerPresets:${dashId}`;

  function safeLsGet(k) {
    try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : null; }
    catch (e) { return null; }
  }
  function safeLsSet(k, v) {
    try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {}
  }

  function toBase64(obj) {
    try { return btoa(unescape(encodeURIComponent(JSON.stringify(obj)))); }
    catch (e) { return ''; }
  }
  function fromBase64(s) {
    try { return JSON.parse(decodeURIComponent(escape(atob(s)))); }
    catch (e) { return null; }
  }

  // Toast helper
  let toastEl = null;
  function showToast(msg) {
    if (!toastEl) {
      toastEl = document.createElement('div');
      toastEl.className = 'sw-toast';
      document.body.appendChild(toastEl);
    }
    toastEl.textContent = msg;
    toastEl.classList.add('sw-show');
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => toastEl.classList.remove('sw-show'), 1800);
  }

  // ------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------
  const SW = {
    _cfg: null,
    _weights: {},     // current weights, keyed by scoringSystem.id
    _defaults: {},    // default weights
    _activeTab: null, // which scoringSystem tab is open in drawer
    _onChange: null,

    init: function (cfg) {
      this._cfg = cfg;
      this._onChange = cfg.onChange || (() => {});
      // Build defaults
      this._defaults = {};
      cfg.scoringSystems.forEach(s => {
        const def = {};
        s.components.forEach(c => { def[c.key] = c.default; });
        this._defaults[s.id] = def;
      });

      // Load weights: URL > localStorage > defaults
      this._weights = JSON.parse(JSON.stringify(this._defaults));
      let urlLoaded = false;
      try {
        const urlParams = new URLSearchParams(window.location.search);
        const enc = urlParams.get('weights');
        if (enc) {
          const obj = fromBase64(enc);
          if (obj) {
            Object.keys(obj).forEach(sid => {
              if (this._weights[sid]) {
                Object.assign(this._weights[sid], obj[sid]);
              }
            });
            urlLoaded = true;
          }
        }
      } catch (e) {}
      if (!urlLoaded) {
        // Fall back to localStorage
        cfg.scoringSystems.forEach(s => {
          const saved = safeLsGet(lsKey(cfg.dashboardId, s.id));
          if (saved) Object.assign(this._weights[s.id], saved);
        });
      }

      this._activeTab = cfg.scoringSystems[0].id;
      this._mountTrigger();
      this._mountBanner();
      this._mountDrawer();
      this._updateTriggerState();
      this._updateBanner();
      // Initial callback (so dashboard renders with restored weights)
      setTimeout(() => this._onChange(this.getWeights()), 0);
    },

    getWeights: function () {
      return JSON.parse(JSON.stringify(this._weights));
    },

    isCustom: function () {
      const d = this._defaults, w = this._weights;
      for (const sid in d) {
        for (const k in d[sid]) {
          if (Math.abs((w[sid][k] || 0) - d[sid][k]) > 0.0001) return true;
        }
      }
      return false;
    },

    reset: function () {
      this._weights = JSON.parse(JSON.stringify(this._defaults));
      // Clear localStorage
      this._cfg.scoringSystems.forEach(s => {
        try { localStorage.removeItem(lsKey(this._cfg.dashboardId, s.id)); } catch (e) {}
      });
      this._rerenderDrawer();
      this._persistAndNotify();
    },

    _persistAndNotify: function () {
      // Save current weights to localStorage
      this._cfg.scoringSystems.forEach(s => {
        safeLsSet(lsKey(this._cfg.dashboardId, s.id), this._weights[s.id]);
      });
      this._updateTriggerState();
      this._updateBanner();
      this._onChange(this.getWeights());
    },

    _mountTrigger: function () {
      const mount = $(this._cfg.triggerSelector);
      if (!mount) return;
      const b = document.createElement('button');
      b.id = 'sw-trigger';
      b.className = 'sw-trigger';
      b.type = 'button';
      b.innerHTML = '<span>⚙</span> <span class="sw-trigger-label">Adjust Weights</span>';
      b.onclick = () => this._openDrawer();
      mount.appendChild(b);
    },

    _updateTriggerState: function () {
      const t = $('#sw-trigger');
      if (!t) return;
      const label = t.querySelector('.sw-trigger-label');
      if (this.isCustom()) {
        t.classList.add('sw-active');
        if (label) label.textContent = 'Adjust Weights (custom)';
      } else {
        t.classList.remove('sw-active');
        if (label) label.textContent = 'Adjust Weights';
      }
    },

    _mountBanner: function () {
      const mount = this._cfg.bannerSelector ? $(this._cfg.bannerSelector) : null;
      if (!mount) return;
      const b = document.createElement('div');
      b.id = 'sw-banner';
      b.className = 'sw-banner' + (this._cfg.theme === 'dark' ? ' sw-banner-dark' : '');
      b.style.display = 'none';
      b.innerHTML = `
        <span class="sw-banner-msg">Custom scoring weights active — rankings reflect your tweaks, not the default methodology.</span>
        <span class="sw-banner-actions">
          <button type="button" data-act="adjust">Adjust</button>
          <button type="button" data-act="share">Copy share link</button>
          <button type="button" data-act="reset">Reset to default</button>
          <button type="button" data-act="dismiss" aria-label="Dismiss">✕</button>
        </span>
      `;
      mount.appendChild(b);
      b.addEventListener('click', e => {
        const act = e.target.dataset.act;
        if (act === 'reset') this.reset();
        else if (act === 'adjust') this._openDrawer();
        else if (act === 'share') this._copyShareLink();
        else if (act === 'dismiss') b.style.display = 'none';
      });
    },

    _updateBanner: function () {
      const b = $('#sw-banner');
      if (!b) return;
      // Don't auto-reshow if user dismissed; but if they re-toggle custom from drawer, show again on next change
      if (this.isCustom()) {
        b.style.display = '';
      } else {
        b.style.display = 'none';
      }
    },

    _mountDrawer: function () {
      const drawer = document.createElement('div');
      drawer.id = 'sw-drawer';
      drawer.className = 'sw-drawer' + (this._cfg.theme === 'dark' ? ' sw-drawer-dark' : '');
      const backdrop = document.createElement('div');
      backdrop.id = 'sw-backdrop';
      backdrop.className = 'sw-backdrop';
      backdrop.onclick = () => this._closeDrawer();
      document.body.appendChild(backdrop);
      document.body.appendChild(drawer);
      this._rerenderDrawer();
    },

    _rerenderDrawer: function () {
      const drawer = $('#sw-drawer');
      if (!drawer) return;
      const cfg = this._cfg;

      const tabsHtml = cfg.scoringSystems.length > 1
        ? `<div class="sw-tabs">${cfg.scoringSystems.map(s =>
            `<button class="sw-tab-btn ${s.id === this._activeTab ? 'sw-active' : ''}" data-tab="${s.id}">${s.tabLabel || s.label}</button>`
          ).join('')}</div>`
        : '';

      const sys = cfg.scoringSystems.find(s => s.id === this._activeTab) || cfg.scoringSystems[0];
      const wt = this._weights[sys.id];
      const def = this._defaults[sys.id];

      const total = sys.components.reduce((sum, c) => sum + (wt[c.key] || 0), 0);
      const target = sys.normalizeTo;
      const totalOk = target == null || Math.abs(total - target) < 0.5;

      const rowsHtml = sys.components.map(c => {
        const v = wt[c.key] != null ? wt[c.key] : c.default;
        const isMod = Math.abs(v - c.default) > 0.0001;
        const step = c.step != null ? c.step : 1;
        const min = c.min != null ? c.min : 0;
        const max = c.max != null ? c.max : 100;
        return `
          <div class="sw-row">
            <div class="sw-row-label">
              <span>${c.label}</span>
              ${c.desc ? `<span class="sw-row-desc">${c.desc}</span>` : ''}
            </div>
            <input type="range" class="sw-slider" data-key="${c.key}" min="${min}" max="${max}" step="${step}" value="${v}">
            <input type="number" class="sw-num ${isMod ? 'sw-modified' : ''}" data-key="${c.key}" min="${min}" max="${max}" step="${step}" value="${v}">
            <span class="sw-default">def ${c.default}</span>
          </div>
        `;
      }).join('');

      // Preset list (cross-system, per dashboard)
      const presets = safeLsGet(lsPresetKey(cfg.dashboardId)) || {};
      const presetOpts = Object.keys(presets).sort().map(n => `<option value="${n}">${n}</option>`).join('');

      drawer.innerHTML = `
        <div class="sw-head">
          <div>
            <div class="sw-title">Score Weights — ${cfg.title || cfg.dashboardId}</div>
            <div class="sw-sub">Adjust how each component contributes to the ranking</div>
          </div>
          <button type="button" class="sw-close" aria-label="Close">×</button>
        </div>
        ${tabsHtml}
        <div class="sw-body">
          <div class="sw-preset-bar">
            <label>Preset:</label>
            <select class="sw-select" id="sw-preset-load">
              <option value="">(none)</option>
              ${presetOpts}
            </select>
            <button type="button" class="sw-btn" id="sw-preset-load-btn">Load</button>
            <input type="text" class="sw-input" id="sw-preset-name" placeholder="Save current as...">
            <button type="button" class="sw-btn" id="sw-preset-save-btn">Save</button>
          </div>
          <div class="sw-section">
            <div class="sw-section-title">${sys.label}${target ? ` &middot; target sum: ${target}` : ''}</div>
            ${rowsHtml}
            ${target != null ? `
              <div class="sw-total ${totalOk ? '' : 'sw-warn'}">
                <span>Total: <strong>${total.toFixed(target % 1 ? 2 : 0)}</strong> ${totalOk ? '✓' : `(target ${target})`}</span>
                ${!totalOk ? '<button type="button" class="sw-total-norm" id="sw-normalize">Normalize</button>' : ''}
              </div>
            ` : ''}
          </div>
        </div>
        <div class="sw-foot">
          <button type="button" class="sw-btn sw-btn-danger" id="sw-reset">Reset all to default</button>
          <button type="button" class="sw-btn" id="sw-share">Copy share link</button>
          <span style="flex:1"></span>
          <button type="button" class="sw-btn sw-btn-primary" id="sw-apply">Apply &amp; Close</button>
        </div>
      `;

      // Wire interactions
      drawer.querySelector('.sw-close').onclick = () => this._closeDrawer();
      drawer.querySelectorAll('.sw-tab-btn').forEach(b => {
        b.onclick = () => { this._activeTab = b.dataset.tab; this._rerenderDrawer(); };
      });

      // Sliders + number inputs
      const debouncedNotify = debounce(() => this._persistAndNotify(), 80);
      drawer.querySelectorAll('.sw-slider, .sw-num').forEach(el => {
        el.addEventListener('input', () => {
          const k = el.dataset.key;
          const v = parseFloat(el.value);
          if (!isNaN(v)) {
            this._weights[sys.id][k] = v;
            // Sync paired input
            const paired = el.classList.contains('sw-slider')
              ? drawer.querySelector(`.sw-num[data-key="${k}"]`)
              : drawer.querySelector(`.sw-slider[data-key="${k}"]`);
            if (paired) paired.value = v;
            // Mark modified
            const numEl = drawer.querySelector(`.sw-num[data-key="${k}"]`);
            if (numEl) numEl.classList.toggle('sw-modified', Math.abs(v - sys.components.find(c => c.key === k).default) > 0.0001);
            // Update total in real time
            this._refreshTotalDisplay(drawer, sys);
            debouncedNotify();
          }
        });
      });

      // Normalize button
      const normBtn = drawer.querySelector('#sw-normalize');
      if (normBtn) {
        normBtn.onclick = () => {
          const total = sys.components.reduce((s, c) => s + (this._weights[sys.id][c.key] || 0), 0);
          if (total <= 0) return;
          const ratio = sys.normalizeTo / total;
          sys.components.forEach(c => {
            this._weights[sys.id][c.key] = +(this._weights[sys.id][c.key] * ratio).toFixed(2);
          });
          this._rerenderDrawer();
          this._persistAndNotify();
        };
      }

      // Reset
      $('#sw-reset').onclick = () => { this.reset(); };

      // Apply & close
      $('#sw-apply').onclick = () => this._closeDrawer();

      // Share
      $('#sw-share').onclick = () => this._copyShareLink();

      // Preset save
      $('#sw-preset-save-btn').onclick = () => {
        const name = $('#sw-preset-name').value.trim();
        if (!name) { showToast('Enter a preset name first'); return; }
        const presets = safeLsGet(lsPresetKey(cfg.dashboardId)) || {};
        presets[name] = JSON.parse(JSON.stringify(this._weights));
        safeLsSet(lsPresetKey(cfg.dashboardId), presets);
        showToast(`Saved preset "${name}"`);
        this._rerenderDrawer();
      };

      // Preset load
      $('#sw-preset-load-btn').onclick = () => {
        const name = $('#sw-preset-load').value;
        if (!name) return;
        const presets = safeLsGet(lsPresetKey(cfg.dashboardId)) || {};
        const p = presets[name];
        if (!p) return;
        // Merge into weights
        Object.keys(p).forEach(sid => {
          if (this._weights[sid]) Object.assign(this._weights[sid], p[sid]);
        });
        this._rerenderDrawer();
        this._persistAndNotify();
        showToast(`Loaded "${name}"`);
      };
    },

    _refreshTotalDisplay: function (drawer, sys) {
      const totalEl = drawer.querySelector('.sw-total');
      if (!totalEl || sys.normalizeTo == null) return;
      const total = sys.components.reduce((s, c) => s + (this._weights[sys.id][c.key] || 0), 0);
      const target = sys.normalizeTo;
      const ok = Math.abs(total - target) < 0.5;
      totalEl.classList.toggle('sw-warn', !ok);
      totalEl.querySelector('strong').textContent = total.toFixed(target % 1 ? 2 : 0);
      // Optionally update the message after the strong
      const span = totalEl.querySelector('span');
      if (span) {
        span.innerHTML = `Total: <strong>${total.toFixed(target % 1 ? 2 : 0)}</strong> ${ok ? '✓' : `(target ${target})`}`;
      }
      // Remove or add normalize button
      let normBtn = totalEl.querySelector('#sw-normalize');
      if (!ok && !normBtn) {
        normBtn = document.createElement('button');
        normBtn.type = 'button';
        normBtn.className = 'sw-total-norm';
        normBtn.id = 'sw-normalize';
        normBtn.textContent = 'Normalize';
        normBtn.onclick = () => {
          const total = sys.components.reduce((s, c) => s + (this._weights[sys.id][c.key] || 0), 0);
          if (total <= 0) return;
          const ratio = sys.normalizeTo / total;
          sys.components.forEach(c => {
            this._weights[sys.id][c.key] = +(this._weights[sys.id][c.key] * ratio).toFixed(2);
          });
          this._rerenderDrawer();
          this._persistAndNotify();
        };
        totalEl.appendChild(normBtn);
      } else if (ok && normBtn) {
        normBtn.remove();
      }
    },

    _openDrawer: function () {
      $('#sw-drawer').classList.add('sw-open');
      $('#sw-backdrop').classList.add('sw-open');
    },

    _closeDrawer: function () {
      $('#sw-drawer').classList.remove('sw-open');
      $('#sw-backdrop').classList.remove('sw-open');
    },

    _copyShareLink: function () {
      const enc = toBase64(this._weights);
      const url = `${location.origin}${location.pathname}?weights=${enc}`;
      if (navigator.clipboard) {
        navigator.clipboard.writeText(url).then(
          () => showToast('Share link copied to clipboard'),
          () => showToast('Copy failed; URL: ' + url.slice(0, 60) + '...')
        );
      } else {
        const ta = document.createElement('textarea');
        ta.value = url;
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); showToast('Share link copied'); }
        catch (e) { showToast('Could not copy'); }
        document.body.removeChild(ta);
      }
    },

    // Returns a string snippet suitable for embedding as a CSV comment block
    csvHeader: function () {
      const lines = ['# Ranger Dashboard Export', `# Date: ${new Date().toISOString()}`];
      if (this.isCustom()) {
        lines.push('# Custom Weights Active:');
        for (const sid in this._weights) {
          for (const k in this._weights[sid]) {
            const v = this._weights[sid][k], def = this._defaults[sid][k];
            if (Math.abs(v - def) > 0.0001) {
              lines.push(`#   ${sid}.${k}: ${v} (default ${def})`);
            }
          }
        }
      } else {
        lines.push('# Default weights');
      }
      return lines.join('\n') + '\n';
    },
  };

  global.ScoreWeights = SW;
})(window);
