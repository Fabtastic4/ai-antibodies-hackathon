/* One scrolling page. Scroll progress, the active nav link, and the speaker-notes panel,
   which shows the note belonging to whichever section is currently on screen. */
(() => {
  const secs = [...document.querySelectorAll('.sec')];
  const links = [...document.querySelectorAll('#nav a')];
  const notes = document.getElementById('notes');
  const fill = document.getElementById('progress-fill');

  // The ranked 20, coloured the way the viewer colours the epitope.
  const strip = document.getElementById('strip');
  for (let r = 1; r <= 20; r++) {
    const c = document.createElement('div');
    c.className = 'cell ' + (r <= 10 ? 'on' : r <= 12 ? 'none' : 'off');
    c.textContent = r;
    strip.appendChild(c);
  }

  let current = secs[0];

  function onScroll() {
    const h = document.documentElement;
    const max = h.scrollHeight - h.clientHeight;
    fill.style.width = (max > 0 ? (h.scrollTop / max) * 100 : 0) + '%';

    // The section covering the middle of the window is the one being presented.
    const mid = window.innerHeight / 2;
    const now = secs.find((s) => {
      const r = s.getBoundingClientRect();
      return r.top <= mid && r.bottom > mid;
    }) || secs[0];

    if (now !== current) {
      current = now;
      links.forEach((a) => a.classList.toggle('on', a.getAttribute('href') === '#' + now.id));
      const aside = now.querySelector('aside');
      notes.textContent = aside ? aside.textContent.replace(/\s+/g, ' ').trim() : '';
    }
  }

  document.getElementById('notes-btn').onclick = () => {
    notes.hidden = !notes.hidden;
    if (!notes.hidden && !notes.textContent) onScroll();
  };

  window.addEventListener('keydown', (e) => {
    // Only when the page itself has focus; inside the viewer iframe the keys are its own.
    if (e.key === 'n' && !e.metaKey && !e.ctrlKey) notes.hidden = !notes.hidden;
  });

  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll);
  onScroll();
})();
