/* Keynote navigation. No dependencies.
   Keys: right / space / PageDown = next, left / PageUp = back, n = speaker notes.
   The live slide hands the window to the viewer in an iframe; while the viewer has focus the
   keys belong to it, so the bar's prev / next buttons are how you leave. */
(() => {
  const slides = [...document.querySelectorAll('.slide')];
  const stage = document.getElementById('stage');
  const live = document.getElementById('live');
  const notes = document.getElementById('notes');
  const count = document.getElementById('count');
  const fill = document.getElementById('progress-fill');
  let at = 0;

  // The ranked 20, coloured the way the viewer colours the epitope.
  const strip = document.getElementById('strip');
  for (let r = 1; r <= 20; r++) {
    const c = document.createElement('div');
    c.className = 'cell ' + (r <= 10 ? 'on' : r <= 12 ? 'none' : 'off');
    c.textContent = r;
    strip.appendChild(c);
  }

  function fit() {
    const wrap = document.getElementById('stage-wrap');
    const s = Math.min(wrap.clientWidth / 1920, wrap.clientHeight / 1080);
    stage.style.setProperty('--s', s);
  }

  function show(i) {
    at = Math.max(0, Math.min(slides.length - 1, i));
    slides.forEach((s, k) => s.classList.toggle('current', k === at));
    const cur = slides[at];
    const isLive = cur.dataset.live !== undefined;
    if (isLive && !live.getAttribute('src')) live.src = cur.dataset.live;
    live.hidden = !isLive;
    stage.hidden = isLive;
    const aside = cur.querySelector('aside');
    notes.textContent = aside ? aside.textContent : '';
    count.textContent = (at + 1) + ' / ' + slides.length;
    fill.style.width = ((at + 1) / slides.length * 100) + '%';
    if (location.hash !== '#' + (at + 1)) history.replaceState(null, '', '#' + (at + 1));
    if (!isLive) window.focus();
  }

  document.getElementById('prev').onclick = () => show(at - 1);
  document.getElementById('next').onclick = () => show(at + 1);
  document.getElementById('notes-btn').onclick = () => { notes.hidden = !notes.hidden; };

  window.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') { e.preventDefault(); show(at + 1); }
    else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); show(at - 1); }
    else if (e.key === 'n') notes.hidden = !notes.hidden;
  });
  window.addEventListener('resize', fit);
  window.addEventListener('hashchange', () => show((parseInt(location.hash.slice(1), 10) || 1) - 1));

  fit();
  show((parseInt(location.hash.slice(1), 10) || 1) - 1);
})();
