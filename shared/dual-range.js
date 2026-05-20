/* ============================================================
   Ranger Dashboards — Shared Dual-Range Slider

   USAGE:
     DualRange.create({
       mount: document.getElementById('mySlider'),
       min: 0, max: 200, step: 1,
       lo: 0, hi: 200,
       label: 'Assets ($M)',
       format: (v) => '$' + v + 'M',
       onChange: (lo, hi) => { applyFilters(); }
     });

   Returns:
     { setRange(lo, hi), getRange() }
   ============================================================ */
(function (global) {
  'use strict';

  function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }

  function create(opts) {
    const mount = opts.mount;
    if (!mount) return null;
    const min = opts.min, max = opts.max, step = opts.step != null ? opts.step : 1;
    const fmt = opts.format || (v => v);
    let lo = opts.lo != null ? opts.lo : min;
    let hi = opts.hi != null ? opts.hi : max;

    mount.classList.add('dr-wrap');
    mount.innerHTML = `
      <div class="dr-label-row">
        <span class="dr-label">${opts.label || ''}</span>
        <span class="dr-values">
          <input type="number" class="dr-input dr-lo-num" min="${min}" max="${max}" step="${step}" value="${lo}">
          <span class="dr-sep">–</span>
          <input type="number" class="dr-input dr-hi-num" min="${min}" max="${max}" step="${step}" value="${hi}">
        </span>
      </div>
      <div class="dr-track-wrap">
        <div class="dr-track"></div>
        <div class="dr-track-fill"></div>
        <input type="range" class="dr-range dr-lo" min="${min}" max="${max}" step="${step}" value="${lo}">
        <input type="range" class="dr-range dr-hi" min="${min}" max="${max}" step="${step}" value="${hi}">
      </div>
    `;

    const loRange = mount.querySelector('.dr-lo');
    const hiRange = mount.querySelector('.dr-hi');
    const loNum = mount.querySelector('.dr-lo-num');
    const hiNum = mount.querySelector('.dr-hi-num');
    const fill = mount.querySelector('.dr-track-fill');

    function repaint() {
      const span = max - min;
      const lp = ((lo - min) / span) * 100;
      const hp = ((hi - min) / span) * 100;
      fill.style.left = lp + '%';
      fill.style.right = (100 - hp) + '%';
      loRange.value = lo;
      hiRange.value = hi;
      loNum.value = lo;
      hiNum.value = hi;
    }

    function commit(emit) {
      // Enforce lo <= hi
      if (lo > hi) { const t = lo; lo = hi; hi = t; }
      lo = clamp(lo, min, max);
      hi = clamp(hi, min, max);
      repaint();
      if (emit !== false && opts.onChange) opts.onChange(lo, hi);
    }

    function onRangeInput(e) {
      const target = e.target;
      const v = parseFloat(target.value);
      if (isNaN(v)) return;
      if (target === loRange) {
        if (v > hi) { lo = hi; loRange.value = lo; }
        else lo = v;
      } else {
        if (v < lo) { hi = lo; hiRange.value = hi; }
        else hi = v;
      }
      commit();
    }

    function onNumInput(e) {
      const target = e.target;
      const v = parseFloat(target.value);
      if (isNaN(v)) return;
      if (target === loNum) lo = v;
      else hi = v;
      commit();
    }

    loRange.addEventListener('input', onRangeInput);
    hiRange.addEventListener('input', onRangeInput);
    loNum.addEventListener('change', onNumInput);
    hiNum.addEventListener('change', onNumInput);

    repaint();

    return {
      setRange(newLo, newHi) {
        if (newLo != null) lo = newLo;
        if (newHi != null) hi = newHi;
        commit(false);
      },
      getRange() { return [lo, hi]; },
    };
  }

  global.DualRange = { create };
})(window);
