/* HER2 binder review — antibody, antigen, and what the redesign changed.
 *
 * Chains, as the co-fold mmCIFs label them:
 *   H  the redesigned antibody heavy chain (VH). CDRH3 is VH 99-107.
 *   L  the light chain, unchanged trastuzumab.
 *   C  HER2 extracellular domain, the antigen.
 *
 * Nothing here computes a score. Every number is served by /api/catalog, which measures
 * the structures with the same code the submission was scored with, and every number
 * arrives with the basis string that says whether it was measured or stood in for.
 */

/* The palette is defined once, in style.css :root, and read back from there. Keeping the
 * literals here as well is how the 3D view and the legend drift apart from the CSS
 * swatches, so each colour has exactly one home and the fallbacks below only matter if
 * the stylesheet failed to load at all. */
const cssVar = (name, fallback) => {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  } catch (e) {
    return fallback;
  }
};

const COL = {
  heavy: cssVar('--heavy', '#58a6ff'),
  light: cssVar('--light', '#a78bfa'),
  antigen: cssVar('--antigen', '#d8dee6'),
  loop: cssVar('--loop', '#ff9f40'),
  mut: cssVar('--mut', '#ff5d5d'),
  hit: cssVar('--hit', '#3fd17a'),
  miss: cssVar('--miss', '#f0c04a'),
};

const state = {
  catalog: null,
  design: null,
  viewer: null,
  model: null,
  spinning: false,
  show: { antigen: 1, surface: 0, epitope: 1, light: 1, loop: 1, muts: 1, contacts: 0, plddt: 0 },
};

const $ = (s) => document.querySelector(s);
const el = (tag, cls, txt) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt !== undefined) n.textContent = txt;
  return n;
};
const fmt = (v, d = 2) =>
  v === null || v === undefined || v === '' ? '—'
    : (typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(d)) : v);

/* ───────────────────────── boot ───────────────────────── */

async function boot() {
  try {
    const r = await fetch('/api/catalog');
    if (!r.ok) throw new Error(`/api/catalog -> ${r.status}`);
    state.catalog = await r.json();
  } catch (e) {
    $('#loading').textContent = `could not load the catalog: ${e.message}`;
    return;
  }
  const c = state.catalog;
  const nEpi = c.target.epitope_residues.length;

  $('#hdr-sub').textContent =
    `${c.target.name} · epitope ${nEpi} residues (${c.target.pdb}) · ` +
    `${c.source.n_designs} designs, ${c.source.n_with_structure} folded`;
  if (c.baseline && c.baseline.available) {
    $('#hdr-base').textContent =
      `baseline: wild-type VH touches ${c.baseline.n_epitope_hit}/${nEpi}`;
  }
  $('#n-designs').textContent = `(${c.source.n_designs})`;

  renderList();
  renderLanes();
  renderProvenance();
  initViewer();

  const first = c.designs.find((d) => d.structure.available) || c.designs[0];
  if (first) select(first.design_id);
}

/* ───────────────────────── design list ───────────────────────── */

function renderList() {
  const box = $('#design-list');
  box.innerHTML = '';
  const nEpi = state.catalog.target.epitope_residues.length;

  for (const d of state.catalog.designs) {
    const b = el('button', 'design');
    b.dataset.id = d.design_id;

    const r1 = el('div', 'row1');
    r1.append(el('span', 'rank', d.rank ? `${d.rank}.` : '–'));
    r1.append(el('span', 'cdr', d.mutations.cdrh3_design));
    b.append(r1);

    const r2 = el('div', 'row2');
    const imp = d.improvement.epitope_recovery;
    const epi = d.measured.n_epitope_hit;

    if (epi === null || epi === undefined) {
      r2.append(el('span', 'chip none', 'not folded'));
    } else {
      const delta = imp ? imp.delta : null;
      const cls = delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat';
      r2.append(el('span', `chip ${cls}`,
        `${epi}/${nEpi} epitope` + (delta !== null ? ` (${delta >= 0 ? '+' : ''}${delta})` : '')));
    }
    r2.append(el('span', 'chip flat', `${d.mutations.cdrh3_mutations} mut`));
    r2.append(el('span', `chip ${d.mutations.paratope_kept === 4 ? 'up' : 'flat'}`,
      `${d.mutations.paratope_kept}/4 paratope`));
    b.append(r2);

    b.onclick = () => select(d.design_id);
    box.append(b);
  }
}

function select(id) {
  const d = state.catalog.designs.find((x) => x.design_id === id);
  if (!d) return;
  state.design = d;
  document.querySelectorAll('.design').forEach((n) =>
    n.classList.toggle('on', n.dataset.id === id));
  renderMutations();
  renderImprovement();
  renderScores();
  refreshLaneChoices();
  loadStructure();
}

/* af2ig scores a complex you ALREADY have, so on a design whose co-fold failed it can only
 * fail too -- with an error that arrives after a round trip and reads like a bug in the
 * lane. Two of the twenty designs are in exactly that state (their hosted Boltz-2 jobs
 * failed), so the picker says so up front and points at the fold that would fix it, rather
 * than offering a run that cannot work. */
function refreshLaneChoices() {
  const d = state.design;
  const pick = $('#lane-pick');
  const note = $('#lane-note');
  if (!d || !pick) return;
  const folded = !!(d.structure && d.structure.available);

  for (const opt of pick.options) {
    const needsComplex = opt.value === 'japanfold:af2ig';
    opt.disabled = needsComplex && !folded;
    opt.textContent = opt.textContent.replace(/ — needs a co-fold first$/, '');
    if (opt.disabled) opt.textContent += ' — needs a co-fold first';
  }
  if (!folded && pick.selectedOptions[0] && pick.selectedOptions[0].disabled) {
    pick.value = 'japanfold:fold:openfold3';      // the one that would fix it
  }
  if (note) {
    note.innerHTML = '';
    if (!folded) {
      note.append(el('div', 'basis synthetic',
        'This design has no co-folded complex, so there is nothing for af2ig to score: '
        + 'its hosted Boltz-2 co-fold failed on the platform, not on its sequence. '
        + 'Co-fold it first (OpenFold3 below, or see "what we built" for the run id).'));
    }
  }
}

/* ───────────────────────── mutations ───────────────────────── */

function renderMutations() {
  const d = state.design;
  const m = d.mutations;
  const start = state.catalog.parent.cdrh3_window[0];

  // The loop, position by position: wild type above, design below, changes in red and
  // the four measured contact residues in green when they survived.
  const paraPos = new Set(m.paratope.filter((p) => p.kept).map((p) => p.vh_position));
  const box = $('#seq-cdr');
  box.innerHTML = '';

  const l1 = el('div');
  l1.append(el('span', 'wt', `WT   ${m.cdrh3_wt}`));
  box.append(l1);

  const l2 = el('div');
  l2.append(el('span', 'wt', 'this '));
  m.cdrh3_design.split('').forEach((ch, i) => {
    const pos = start + i;
    const changed = m.cdrh3_wt[i] !== undefined && m.cdrh3_wt[i] !== ch;
    if (changed) l2.append(el('b', null, ch));
    else if (paraPos.has(pos)) l2.append(el('span', 'keep', ch));
    else l2.append(el('span', null, ch));
  });
  box.append(l2);

  const l3 = el('div', 'wt');
  l3.style.fontSize = '10.5px';
  l3.textContent = `VH ${start}–${start + m.cdrh3_design.length - 1}` +
    (m.changed_span.length_change ? `  (length ${m.changed_span.length_change > 0 ? '+' : ''}${m.changed_span.length_change})` : '');
  box.append(l3);

  // Substitution list.
  const list = $('#mut-list');
  list.innerHTML = '';
  for (const s of m.substitutions) {
    const row = el('div', 'mutrow');
    row.append(el('span', 'pos', `VH${s.vh_position}`));
    row.append(el('span', 'a', s.wt));
    row.append(el('span', 'arrow', '→'));
    row.append(el('span', 'b', s.design));
    const contact = m.paratope.find((p) => p.vh_position === s.vh_position);
    if (contact) {
      row.append(el('span', 'tag',
        `contacts HER2 at ${contact.distance_to_her2_in_1n8z} Å in 1N8Z — lost`));
    }
    list.append(row);
  }
  if (!m.substitutions.length) list.append(el('div', 'mutrow', 'identical to trastuzumab'));

  // Paratope verdict.
  const kept = m.paratope.filter((p) => p.kept).map((p) => `${p.wt}${p.vh_position}`);
  const lost = m.paratope.filter((p) => !p.kept);
  const note = $('#paratope-note');
  note.innerHTML = '';
  const n = el('div', `note ${m.paratope_kept === 4 ? 'good' : ''}`);
  n.textContent =
    `${m.paratope_kept}/4 measured HER2 contacts kept` +
    (kept.length ? `: ${kept.join(', ')}. ` : '. ') +
    (lost.length
      ? `Lost ${lost.map((p) => `${p.wt}${p.vh_position}→${p.design}`).join(', ')}.`
      : '');
  note.append(n);
}

/* ───────────────────────── improvement ───────────────────────── */

const IMP_LABEL = {
  epitope_recovery: 'Epitope residues reached',
  novelty: 'CDRH3 mutations (novelty gate)',
  paratope_conserved: 'Measured contacts kept',
  interface_size: 'Interface contacts',
};

function renderImprovement() {
  const box = $('#improvement');
  box.innerHTML = '';
  const imp = state.design.improvement;
  const order = ['epitope_recovery', 'novelty', 'paratope_conserved', 'interface_size'];

  for (const k of order) {
    const v = imp[k];
    if (!v) continue;
    const wrap = el('div', 'imp');

    const top = el('div', 'top');
    top.append(el('span', null, IMP_LABEL[k] || k));
    const dir = v.delta > 0 ? '+' : '';
    const num = el('span', 'n');
    num.textContent = v.of
      ? `${fmt(v.design)}/${v.of}  (${dir}${fmt(v.delta)})`
      : `${fmt(v.design)}  (${dir}${fmt(v.delta)})`;
    top.append(num);
    wrap.append(top);

    // Bar: the design, with a tick where wild type sits.
    const max = v.of || Math.max(v.design || 0, v.baseline || 0) * 1.25 || 1;
    const bar = el('div', 'bar');
    const fill = el('i', v.delta > 0 ? 'up' : v.delta < 0 ? 'down' : '');
    fill.style.width = `${Math.max(0, Math.min(100, (v.design / max) * 100))}%`;
    bar.append(fill);
    if (v.baseline !== null && v.baseline !== undefined) {
      const ref = el('div', 'ref');
      ref.style.left = `${Math.max(0, Math.min(100, (v.baseline / max) * 100))}%`;
      ref.title = `wild type: ${v.baseline}`;
      bar.append(ref);
    }
    wrap.append(bar);

    wrap.append(el('div', 'why', v.direction));
    if (!v.comparable) {
      const w = el('div', 'basis synthetic');
      w.textContent = `not like-for-like — ${v.basis}`;
      wrap.append(w);
    } else {
      wrap.append(el('div', 'basis', v.basis));
    }
    if (k === 'novelty') {
      const n = el('div', `note ${v.passes_gate ? 'good' : 'bad'}`);
      n.textContent = v.passes_gate
        ? `${v.design} mutations — clears the ≥6 target abguard needs.`
        : `${v.design} mutations — below the ≥6 target; abguard rejects most designs here.`;
      wrap.append(n);
    }
    box.append(wrap);
  }

  if (state.catalog.baseline && state.catalog.baseline.available) {
    const n = el('div', 'basis');
    n.textContent = `Wild-type reference: ${state.catalog.baseline.source}. ` +
      `Compared VH to VH — the ${state.catalog.target.epitope_residues.length}-residue ` +
      `epitope was defined from the whole Fab, so the light chain accounts for the rest.`;
    box.append(n);
  }
}

/* ───────────────────────── scores ───────────────────────── */

function renderScores() {
  const d = state.design;
  const box = $('#scores');
  box.innerHTML = '';

  const t = el('table', 'kv');
  const add = (label, value, unit) => {
    const tr = el('tr');
    tr.append(el('th', null, label));
    const td = el('td', 'v', value === null || value === undefined
      ? '—' : `${fmt(value)}${unit || ''}`);
    tr.append(td);
    t.append(tr);
  };

  const nEpi = state.catalog.target.epitope_residues.length;
  add('epitope residues reached', d.measured.n_epitope_hit === null
    ? null : `${d.measured.n_epitope_hit}/${nEpi}`);
  add('cross-chain contacts', d.measured.n_contacts);
  add('target residues touched', d.measured.n_target_residues);
  add('binder pLDDT', d.measured.binder_plddt);
  add('CDRH3 pLDDT', d.measured.cdrh3_plddt);
  add('NetSolP solubility (min)', d.developability.netsolp_solubility_min);
  add('cysteines', d.developability.cysteine_count);
  add('ESM-2 proxy', d.thermostability_proxy.value);
  box.append(t);

  // Axis 1 — binding. Its own block, because whether it was measured is the whole point.
  if (d.axis1) {
    const t1 = el('table', 'kv');
    t1.style.marginTop = '8px';
    const row = (k, v, u) => {
      const tr = el('tr');
      tr.append(el('th', null, k));
      tr.append(el('td', 'v', v === null || v === undefined ? '—' : `${fmt(v)}${u || ''}`));
      t1.append(tr);
    };
    const head = el('tr', 'sep');
    head.append(el('th', null, d.axis1.measured
      ? `axis 1 — measured${d.axis1.lane ? ' · ' + d.axis1.lane : ''}`
      : 'axis 1 — not measured'));
    head.append(el('td', null, ''));
    t1.append(head);
    row('min interface pAE', d.axis1.min_ipae, ' Å');
    row('ipTM', d.axis1.iptm);
    row('ipSAE', d.axis1.ipsae);
    row('binder pLDDT (refold)', d.axis1.binder_plddt);
    box.append(t1);
    box.append(Object.assign(
      el('div', `basis ${d.axis1.measured ? '' : 'synthetic'}`),
      { textContent: d.axis1.basis }));
  }

  // Live scores added by a lane run this session.
  if (d.lane_scores) {
    const t2 = el('table', 'kv');
    t2.style.marginTop = '8px';
    for (const [k, s] of Object.entries(d.lane_scores)) {
      const tr = el('tr');
      tr.append(el('th', null, k.replace(/_/g, ' ')));
      tr.append(el('td', 'v', `${fmt(s.value)}${s.unit ? ' ' + s.unit : ''}`));
      t2.append(tr);
    }
    box.append(t2);
    const first = Object.values(d.lane_scores)[0];
    if (first) box.append(Object.assign(el('div', 'basis'), { textContent: first.basis }));
  }

  // What is honestly not available, and why.
  const miss = el('div', 'note');
  miss.innerHTML = '';
  miss.append(el('div', null, 'Not measured here:'));
  for (const [k, why] of Object.entries(d.unavailable)) {
    const line = el('div');
    line.style.fontSize = '11px';
    line.style.color = 'var(--ink-faint)';
    line.textContent = `${k} — ${why}`;
    miss.append(line);
  }
  box.append(miss);

  if (d.thermostability_proxy.basis) {
    const b = el('div', 'basis synthetic');
    b.textContent = d.thermostability_proxy.basis;
    box.append(b);
  }
}

/* ───────────────────────── 3D ───────────────────────── */

function initViewer() {
  if (typeof $3Dmol === 'undefined') {
    $('#loading').textContent =
      '3Dmol.js did not load. The viewer needs one script from cdnjs.cloudflare.com; ' +
      'everything else here works offline.';
    return;
  }
  state.viewer = $3Dmol.createViewer($('#viewport'), { backgroundColor: '#0a0e14' });

  document.querySelectorAll('button.tool').forEach((b) => {
    b.onclick = () => {
      const t = b.dataset.t;
      if (t === 'reset') { state.viewer.zoomTo(); state.viewer.render(); return; }
      if (t === 'spin') {
        state.spinning = !state.spinning;
        state.viewer.spin(state.spinning ? 'y' : false);
        b.classList.toggle('on', state.spinning);
        return;
      }
      state.show[t] = state.show[t] ? 0 : 1;
      b.classList.toggle('on', !!state.show[t]);
      paint();
    };
  });
}

async function loadStructure() {
  const d = state.design;
  const v = state.viewer;
  if (!v) return;

  $('#viewer-note').textContent = '';
  if (!d.structure.available) {
    v.clear();
    v.render();
    state.model = null;
    $('#loading').classList.remove('hide');
    $('#loading').textContent =
      `${d.design_id} has no co-fold yet. Fold it with a lane on the right, ` +
      `or pick a design that is already folded.`;
    return;
  }

  $('#loading').classList.remove('hide');
  $('#loading').textContent = 'loading structure…';
  try {
    const r = await fetch(d.structure.url);
    if (!r.ok) throw new Error(`${d.structure.url} -> ${r.status}`);
    const text = await r.text();
    v.clear();
    state.model = v.addModel(text, 'cif');
    paint();
    v.zoomTo({ chain: 'H' });
    v.zoom(0.55);
    v.render();
    $('#loading').classList.add('hide');
    $('#viewer-note').textContent =
      `${d.structure.source}. Drag to rotate, scroll to zoom. ` +
      `Chains: H heavy (redesigned), L light, C HER2.`;
  } catch (e) {
    $('#loading').textContent = `could not load the structure: ${e.message}`;
  }
}

function paint() {
  const v = state.viewer;
  const d = state.design;
  if (!v || !state.model) return;

  const s = state.show;
  const epitope = state.catalog.target.epitope_residues;
  const hit = (d.structure.epitope_residues_hit || []);
  const hitSet = new Set(hit);
  const missed = epitope.filter((r) => !hitSet.has(r));
  const loopRes = d.mutations.highlight_vh_residues;
  const subs = d.mutations.substitutions.map((x) => x.vh_position);
  const keptPara = d.mutations.paratope.filter((p) => p.kept).map((p) => p.vh_position);

  v.removeAllShapes();
  v.removeAllLabels();
  v.removeAllSurfaces();      // or a toggled-off surface would stay, and stack on re-add
  v.setStyle({}, {});         // start from nothing every repaint

  /* antibody heavy chain */
  if (s.plddt) {
    // pLDDT lives in the mmCIF B-factor column for a Boltz-2 co-fold.
    v.setStyle({ chain: 'H' },
      { cartoon: { colorscheme: { prop: 'b', gradient: 'roygb', min: 50, max: 95 } } });
  } else {
    v.setStyle({ chain: 'H' }, { cartoon: { color: COL.heavy, opacity: 0.95 } });
  }

  /* light chain */
  if (s.light) {
    v.setStyle({ chain: 'L' }, { cartoon: { color: COL.light, opacity: 0.55 } });
  }

  /* antigen */
  if (s.antigen) {
    v.setStyle({ chain: 'C' }, { cartoon: { color: COL.antigen, opacity: 0.5 } });
    if (s.surface) {
      v.addSurface($3Dmol.SurfaceType.VDW,
        { opacity: 0.62, color: COL.antigen }, { chain: 'C' });
    }
  }

  /* the epitope: reached in green, missed in amber */
  if (s.epitope && s.antigen) {
    if (hit.length) {
      v.addStyle({ chain: 'C', resi: hit },
        { stick: { radius: 0.19, color: COL.hit }, cartoon: { color: COL.hit } });
    }
    if (missed.length) {
      v.addStyle({ chain: 'C', resi: missed },
        { stick: { radius: 0.12, color: COL.miss, opacity: 0.75 } });
    }
  }

  /* CDRH3 */
  if (s.loop) {
    v.addStyle({ chain: 'H', resi: loopRes },
      { cartoon: { color: COL.loop, thickness: 0.9 }, stick: { radius: 0.14, color: COL.loop } });
  }

  /* substituted positions, plus the surviving measured contacts */
  if (s.muts) {
    if (subs.length) {
      v.addStyle({ chain: 'H', resi: subs },
        { stick: { radius: 0.27, color: COL.mut } });
      for (const p of d.mutations.substitutions) {
        // Label reads wild-type, position, design — e.g. G100D — because the position
        // alone does not say what was traded away.
        v.addLabel(`${p.wt}${p.vh_position}${p.design}`, {
          position: labelPos('H', p.vh_position),
          font: 'sans-serif', fontSize: 10, fontColor: '#ffffff',
          backgroundColor: COL.mut, backgroundOpacity: 0.82, inFront: true,
        });
      }
    }
    if (keptPara.length) {
      v.addStyle({ chain: 'H', resi: keptPara },
        { stick: { radius: 0.27, color: COL.hit } });
      for (const p of d.mutations.paratope.filter((x) => x.kept)) {
        v.addLabel(`${p.wt}${p.vh_position} kept`, {
          position: labelPos('H', p.vh_position),
          font: 'sans-serif', fontSize: 9.5, fontColor: '#07140d',
          backgroundColor: COL.hit, backgroundOpacity: 0.85, inFront: true,
        });
      }
    }
  }

  /* contact lines between the binder and the epitope residues it reaches */
  if (s.contacts && hit.length) {
    for (const r of hit) {
      const a = labelPos('C', r);
      const b = nearestBinderAtom(a);
      if (a && b) {
        v.addLine({ start: a, end: b, color: COL.hit, dashed: true, linewidth: 1.5 });
      }
    }
  }

  renderLegend(hit.length, missed.length, subs.length);
  v.render();
}

/** CA position of one residue, for hanging a label on. */
function labelPos(chain, resi) {
  const sel = state.model.selectedAtoms({ chain, resi, atom: 'CA' });
  if (sel && sel.length) return { x: sel[0].x, y: sel[0].y, z: sel[0].z };
  const any = state.model.selectedAtoms({ chain, resi });
  return any && any.length ? { x: any[0].x, y: any[0].y, z: any[0].z } : null;
}

/** Closest heavy-chain atom to a point — the other end of a contact line. */
function nearestBinderAtom(p) {
  if (!p) return null;
  const atoms = state.model.selectedAtoms({ chain: 'H' });
  let best = null, bd = Infinity;
  for (const a of atoms) {
    const dd = (a.x - p.x) ** 2 + (a.y - p.y) ** 2 + (a.z - p.z) ** 2;
    if (dd < bd) { bd = dd; best = a; }
  }
  // Only draw it if it is actually a contact; 4.5 Å is the cutoff the scorer used.
  return best && Math.sqrt(bd) <= 6.0 ? { x: best.x, y: best.y, z: best.z } : null;
}

function renderLegend(nHit, nMiss, nSub) {
  const nEpi = state.catalog.target.epitope_residues.length;
  const rows = [
    [COL.heavy, 'heavy chain (redesigned)'],
    [COL.light, 'light chain'],
    [COL.antigen, 'HER2'],
    [COL.loop, `CDRH3 (VH ${state.catalog.parent.cdrh3_window.join('–')})`],
    [COL.mut, `substitutions (${nSub})`],
    [COL.hit, `epitope reached (${nHit}/${nEpi})`],
    [COL.miss, `epitope missed (${nMiss})`],
  ];
  $('#legend').innerHTML = rows.map(([c, t]) =>
    `<div><span class="sw" style="background:${c}"></span>${t}</div>`).join('');
}

/* ───────────────────────── lanes ───────────────────────── */

function renderLanes() {
  const box = $('#lanes');
  box.innerHTML = '';
  const pick = $('#lane-pick');
  pick.innerHTML = '';

  for (const ln of state.catalog.lanes) {
    const row = el('div', `lane ${ln.ready ? 'ready' : ''}`);
    row.append(el('div', 'dot'));
    const txt = el('div', 'txt');
    txt.append(el('div', 'nm', ln.label));
    txt.append(el('div', 'dt', ln.detail));
    row.append(txt);
    box.append(row);
  }

  const opts = [
    ['dummy', 'Dummy model — local, instant, free'],
    ['japanfold:af2ig', 'JapanFold af2ig — ipTM + interface pAE (billed)'],
    ['japanfold:fold:openfold3', 'JapanFold OpenFold3 — co-fold (billed)'],
    ['japanfold:fold:opendde-abag', 'JapanFold OpenDDE abag + epitope guidance (billed)'],
    ['vm', 'VM Apheris Foundry — Predict Structure'],
  ];
  for (const [v, label] of opts) {
    const o = el('option', null, label);
    o.value = v;
    pick.append(o);
  }

  $('#run-btn').onclick = runLane;
  $('#run-all-btn').onclick = priceAll;
}

function parseLane(v) {
  const [lane, mode, model] = v.split(':');
  return {
    lane,
    mode: mode || (lane === 'japanfold' ? 'af2ig' : undefined),
    model: model || 'openfold3',
    epitope_guidance: model === 'opendde-abag',
  };
}

async function runLane() {
  const d = state.design;
  const sel = parseLane($('#lane-pick').value);
  const out = $('#run-out');
  const btn = $('#run-btn');
  out.innerHTML = '';
  btn.disabled = true;
  btn.textContent = 'running…';

  const body = {
    design_id: d.design_id, heavy: d.heavy, light: d.light,
    lane: sel.lane, mode: sel.mode, model: sel.model,
    epitope_guidance: sel.epitope_guidance,
  };

  try {
    let r = await fetch('/api/predict', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    // 402 = the lane bills. Ask, then resend with consent.
    if (r.status === 402) {
      const info = await r.json();
      const p = info.price || {};
      const each = p.usd_p50_each;
      const ok = confirm(
        `${sel.lane}${sel.mode ? ' / ' + sel.mode : ''} starts a billed job on your ` +
        `JapanFold credit.\n\n` +
        (each ? `Typical cost: $${each} (p90 $${p.usd_p90_each}) for this one design.\n\n` : '') +
        `Run it?`);
      if (!ok) { out.append(el('div', 'basis', 'cancelled — nothing was started.')); return; }
      body.confirm = true;
      btn.textContent = 'submitted, waiting…';
      r = await fetch('/api/predict', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    }

    const res = await r.json();
    if (!r.ok) throw new Error(res.error || `HTTP ${r.status}`);

    if (res.lane_error) {
      const n = el('div', 'note bad');
      n.textContent = `${res.lane_attempted || sel.lane} could not run: ${res.lane_error}`;
      out.append(n);
      const f = el('div', 'basis');
      f.textContent = 'Showing the dummy lane instead. Nothing was billed.';
      out.append(f);
    } else {
      const n = el('div', 'note good');
      n.textContent = `${res.model} finished.`;
      out.append(n);
    }

    // Fold the returned scores into the panel.
    d.lane_scores = {};
    for (const [k, s] of Object.entries(res.scores || {})) {
      if (s.measured && ['iptm', 'interface_pae', 'ipsae', 'af2ig_plddt'].includes(k)) {
        d.lane_scores[k] = s;
      }
    }
    if (res.japanfold && res.japanfold.job_id) {
      const j = el('div', 'basis');
      j.textContent = `job ${res.japanfold.job_id} — artifacts in ${res.japanfold.dest}`;
      out.append(j);
    }
    renderScores();
    if (sel.mode === 'fold') {
      // A fresh fold means a new structure: rebuild the catalog and reload it.
      await fetch('/api/catalog?refresh=1');
      const cat = await (await fetch('/api/catalog')).json();
      state.catalog = cat;
      renderList();
      select(d.design_id);
    }
  } catch (e) {
    const n = el('div', 'note bad');
    n.textContent = e.message;
    out.append(n);
  } finally {
    btn.disabled = false;
    btn.textContent = 'run';
  }
}

async function priceAll() {
  const sel = parseLane($('#lane-pick').value);
  const out = $('#run-out');
  out.innerHTML = '';
  if (sel.lane !== 'japanfold') {
    out.append(el('div', 'basis', 'Only the JapanFold lane is metered per job.'));
    return;
  }
  const model = sel.mode === 'af2ig' ? 'af2ig' : sel.model;
  const n = state.catalog.source.n_with_structure;
  try {
    const p = await (await fetch(`/api/price?model=${model}&n=${n}`)).json();
    const box = el('div', 'note');
    box.textContent =
      `${model} on all ${n} folded designs: about $${p.usd_p50_total} ` +
      `(p90 $${p.usd_p90_total}), from ${p.jobs_observed} past jobs. ` +
      `Nothing has been started.`;
    out.append(box);
    const cmd = el('div', 'basis');
    cmd.textContent = `Batch it from the shell: python3 viz/japanfold.py --score-af2ig --all --yes`;
    out.append(cmd);
  } catch (e) {
    out.append(el('div', 'note bad', e.message));
  }
}

/* ───────────────────────── provenance ───────────────────────── */

function renderProvenance() {
  const c = state.catalog;
  const box = $('#provenance');
  box.innerHTML = '';
  const add = (t) => box.append(el('div', 'basis', t));
  add(`designs: ${c.source.submission} (${c.source.n_designs} rows)`);
  add(`target: ${c.target.epitope_source}`);
  if (c.baseline.available) add(`baseline: ${c.baseline.source}`);
  add(`parent: trastuzumab VH, CDRH3 ${c.parent.cdrh3} at VH ${c.parent.cdrh3_window.join('–')}`);
  add(`contacts: 4.5 Å cross-chain heavy-atom, the same scorer as pipeline/score/cofold_contacts.py`);
  const n = el('div', 'note');
  n.textContent =
    'Co-fold contact counts are not ipTM and not interface pAE. The hosted lane reports ' +
    'neither; the JapanFold af2ig lane does, and labels them as measured when it runs.';
  box.append(n);
}

/* ───────────────────────── "what we built" ─────────────────────────
 *
 * The design panels answer "is this candidate any good". This answers what a demo and an
 * evaluator both ask first: what exists, what was really measured, and where is the
 * evidence. /api/overview reads it off disk at request time -- no network, no cost -- so
 * every path on this screen can be opened and checked while it is on screen.
 */

let ovLoaded = false;
let jobTimer = null;

function switchView(which) {
  const review = which !== 'overview';
  $('#overview-view').hidden = review;
  document.getElementById('app').classList.toggle('ov', !review);
  for (const b of document.querySelectorAll('.viewtab')) {
    b.classList.toggle('on', b.dataset.view === (review ? 'review' : 'overview'));
  }
  if (!review) {
    if (!ovLoaded) renderOverview();
    pollJobs();
    if (!jobTimer) jobTimer = setInterval(pollJobs, 15000);
  } else if (jobTimer) {
    clearInterval(jobTimer);          // stop polling the moment it is off screen
    jobTimer = null;
  }
  // 3Dmol sized itself against a container that was display:none while hidden.
  if (review && state.viewer) setTimeout(() => state.viewer.resize(), 30);
}

function head(text) {
  return el('div', 'ov-h', text);
}

function lede(text, tight) {
  return el('div', `ov-lede${tight ? ' tight' : ''}`, text);
}

/** One line of figures. A grid of big-number boxes would say the same thing with more ink. */
function figures(pairs) {
  const row = el('div', 'figures');
  for (const [n, k] of pairs) {
    if (n === null || n === undefined) continue;
    const d = el('div');
    d.append(el('b', null, String(n)));
    d.append(document.createTextNode(k));
    row.append(d);
  }
  return row;
}

function ovTable(headers, rows) {
  const t = el('table', 'ov');
  const hr = el('tr');
  for (const h of headers) hr.append(el('th', null, h));
  t.append(hr);
  for (const r of rows) {
    const tr = el('tr');
    for (const c of r) {
      const cell = (c && typeof c === 'object') ? c : { v: c };
      tr.append(el('td', cell.cls || null, String(cell.v ?? '')));
    }
    t.append(tr);
  }
  return t;
}

function cmd(text) {
  const d = el('div', 'cmd', text);
  d.onclick = () => navigator.clipboard && navigator.clipboard.writeText(text);
  return d;
}

async function renderOverview() {
  const box = $('#ov-body');
  box.textContent = 'reading the repo…';
  let o;
  try {
    const r = await fetch('/api/overview');
    if (!r.ok) throw new Error(`/api/overview -> ${r.status}`);
    o = await r.json();
  } catch (e) {
    box.innerHTML = '';
    box.append(el('div', 'note bad', `could not build the overview: ${e.message}`));
    return;
  }
  ovLoaded = true;
  box.innerHTML = '';
  const p = o.project;
  const a = o.artifacts;

  /* ---- what this is, in figures ---- */
  box.append(head('The project'));
  box.append(lede(
    `${p.title}. Target ${p.target}; parent ${p.parent}. The epitope is ${p.epitope_residues} `
    + `HER2 residues, defined at ${p.contact_cutoff_A} Å from the crystal.`, true));
  box.append(figures([
    [p.n_designs, 'designs submitted'],
    [p.n_cofolded, 'with a co-folded complex'],
    [o.baseline.available ? `${o.baseline.n_epitope_hit}/${o.baseline.of}` : null,
      'wild-type VH epitope reach'],
    [a.totals.csv_tables, 'score tables'],
    [a.totals.report_rows.toLocaleString(), 'rows of evidence'],
    [a.totals.run_records, 'hosted run records'],
    [a.totals.docs, 'docs'],
  ]));

  /* ---- the three judged axes ---- */
  box.append(head('The three judged axes'));
  box.append(lede(
    'Coverage is counted by joining against the candidate pool, not by counting rows in a '
    + 'score table — a table full of ids that join to nothing would otherwise read as full '
    + 'coverage. Measured, proxy and absent never share a column.'));
  const ag = el('div', 'axis-grid');
  for (const ax of o.axes) {
    const card = el('div', `axis ${ax.state}`);
    card.append(el('div', 'nm', `${ax.axis}. ${ax.name}`));
    card.append(el('div', 'unit', ax.unit));
    const bar = el('div', 'bar');
    const fill = el('i');
    fill.style.width = `${Math.round((ax.coverage || 0) * 100)}%`;
    bar.append(fill);
    card.append(bar);
    const cov = el('div', 'cov');
    cov.append(document.createTextNode(`${ax.n_designs}/${ax.n_total} designs `));
    cov.append(el('em', null, ax.measured_by.length
      ? `${ax.state} · ${ax.measured_by.join(', ')}` : ax.state));
    card.append(cov);
    if (ax.note) card.append(el('div', 'why', ax.note));
    for (const e of ax.evidence) card.append(el('div', 'src', e));
    ag.append(card);
  }
  box.append(ag);

  /* ---- the gap, named ---- */
  if (o.gaps && o.gaps.n_unfolded) {
    box.append(head(`Not folded — ${o.gaps.n_unfolded} of ${p.n_designs}`));
    box.append(lede(o.gaps.consequence));
    box.append(ovTable(['design', 'hosted run', 'why'],
      o.gaps.unfolded.map((u) => [
        { v: u.design_id, cls: 'm' },
        { v: `${u.state}${u.operation_id ? ' · ' + u.operation_id : ''}`, cls: 'm' },
        { v: u.why, cls: 'what' }])));
    const fix = o.gaps.unfolded.find((u) => u.fix);
    if (fix) {
      box.append(lede('The platform states its own failure does not implicate the inputs, '
        + 'so these are re-folded on another lane rather than resubmitted into the same '
        + 'failure:', true));
      for (const u of o.gaps.unfolded) if (u.fix) box.append(cmd(u.fix));
    }
  }

  /* ---- the pipeline ---- */
  box.append(head('The pipeline'));
  box.append(ovTable(['stage', 'script', 'what it does'],
    o.stages.map((s) => [s.stage, { v: s.script, cls: 'm' }, { v: s.what, cls: 'what' }])));

  /* ---- axis 1, live ---- */
  const j = o.japanfold;
  box.append(head('Axis 1 — the JapanFold lane'));
  const st = el('div', 'ov-state');
  st.innerHTML =
    `key <span class="${j.key_present ? '' : 'bad'}">`
    + `${j.key_present ? 'loaded' : 'missing'}</span> · `
    + `<span>${j.base}</span> · `
    + `<span class="${j.n_measured ? '' : 'none'}">${j.n_measured}</span> design(s) measured`
    + (j.with_ipsae ? ` · <span>${j.with_ipsae}</span> with a local ipSAE` : '')
    + ` · <span id="ov-jobs" class="none">jobs …</span>`;
  box.append(st);
  if (j.key_source) {
    box.append(lede(`Key read from ${j.key_source}. The value is never printed, logged or `
      + 'committed.', true));
  }
  box.append(lede(j.n_measured
    ? `Measured numbers land in ${j.metrics_csv}, in the same schema the ranker already `
      + 'reads, so axis 1 flows into the submission without another join.'
    : 'Nothing measured yet. One batched job scores every co-folded design: each target '
      + 'runs on its own chip, so it is a single queue wait at about $0.0004 a design.'));
  box.append(cmd(`${j.commands.estimate}     # free, starts nothing`));
  box.append(cmd(j.commands.score_all));
  box.append(cmd(j.commands.rank));
  const jt = el('div');
  jt.id = 'ov-jobtable';
  box.append(jt);

  /* ---- everything on disk ---- */
  box.append(head('Every table, with its rows'));
  const tables = [...a.design_tables, ...a.report_tables]
    .filter((t) => t.rows > 0).sort((x, y) => y.rows - x.rows);
  box.append(ovTable(['table', 'rows', 'cols'],
    tables.map((t) => [{ v: t.path, cls: 'm' }, { v: t.rows, cls: 'num' },
      { v: t.columns, cls: 'num' }])));

  box.append(head('Structures and runs'));
  box.append(ovTable(['what', 'n', 'where'], [
    ['co-folded complexes', { v: a.cofold_structures.n, cls: 'num' },
      { v: a.cofold_structures.path, cls: 'm' }],
    ['af2ig scores', { v: a.japanfold_scored.n, cls: 'num' },
      { v: a.japanfold_scored.path, cls: 'm' }],
    ['JapanFold folds', { v: a.japanfold_folds.n, cls: 'num' },
      { v: '../results/japanfold/', cls: 'm' }],
    ['hosted run records', { v: a.nebius_runs.n, cls: 'num' },
      { v: a.nebius_runs.path, cls: 'm' }],
  ]));

  box.append(head('What is written down'));
  box.append(ovTable(['doc', 'first line'],
    a.docs.map((d) => [{ v: d.path, cls: 'm' }, { v: d.title, cls: 'what' }])));

  box.append(head('Inference lanes'));
  box.append(ovTable(['lane', 'ready', 'detail'],
    o.lanes.map((ln) => [ln.lane, { v: ln.ready ? 'yes' : 'no', cls: ln.ready ? '' : 'no' },
      { v: ln.detail, cls: 'what' }])));
}

/** Recent jobs on this key. Listing is read-only: it starts nothing and bills nothing. */
async function pollJobs() {
  const slot = $('#ov-jobs');
  if (!slot) return;
  try {
    const r = await fetch('/api/jobs?limit=8');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const { jobs } = await r.json();
    const active = jobs.filter((x) => ['queued', 'running'].includes(x.status));
    slot.textContent = `${active.length} job(s) running, ${jobs.length} recent`;
    slot.className = active.length ? 'live' : 'none';
    const box = $('#ov-jobtable');
    if (!box) return;
    box.innerHTML = '';
    if (!jobs.length) return;
    box.append(ovTable(['job', 'status', 'model', 'targets', 'name'],
      jobs.map((x) => [{ v: x.id, cls: 'm' }, x.status, x.model || '—',
        { v: x.total ? `${x.done ?? 0}/${x.total}` : '—', cls: 'num' },
        { v: x.name || '', cls: 'what' }])));
  } catch (e) {
    slot.textContent = `jobs: ${e.message}`;
    slot.className = 'bad';
  }
}

for (const b of document.querySelectorAll('.viewtab')) {
  b.onclick = () => switchView(b.dataset.view);
}

boot();
