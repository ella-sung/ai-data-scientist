/* Charting + dashboard behaviour. No dependencies, no CDN, works offline.
   Everything recomputes from CUBE on every filter change. */

const C = {
  risk: '#A3324B', hold: '#14655F', watch: '#9A6B12',
  mute: '#66707A', rule: '#D6DAD5', ink: '#0F1A22'
};

const el = id => document.getElementById(id);
const fmtPct = v => (v * 100).toFixed(1) + '%';
const fmtInt = v => Math.round(v).toLocaleString();
const fmtUsd = v => '$' + Math.round(v).toLocaleString();

/* ---------- tiny SVG chart kit ------------------------------------------ */

function frame(node, h) {
  const w = Math.max(node.clientWidth || 520, 260);
  return { w, h, m: { t: 16, r: 14, b: 38, l: 52 },
           iw: w - 66, ih: h - 54 };
}

function axis(f, ticks, fmt) {
  let s = '';
  ticks.forEach(t => {
    const y = f.m.t + f.ih - t.p * f.ih;
    s += `<line x1="${f.m.l}" y1="${y}" x2="${f.m.l + f.iw}" y2="${y}"
           stroke="${C.rule}" stroke-width="1"/>`;
    s += `<text x="${f.m.l - 8}" y="${y + 4}" text-anchor="end"
           font-size="11" fill="${C.mute}">${fmt(t.v)}</text>`;
  });
  return s;
}

function scale(max) {
  const nice = [0, 0.25, 0.5, 0.75, 1].map(p => ({ p, v: max * p }));
  return nice;
}

function barChart(node, { labels, values, colors, fmt = fmtPct, note }) {
  const f = frame(node, 250);
  const max = Math.max(...values, 1e-9) * 1.18;
  const bw = f.iw / labels.length;
  let s = `<svg viewBox="0 0 ${f.w} ${f.h}" width="100%" height="${f.h}" role="img">`;
  s += axis(f, scale(max), fmt);
  labels.forEach((l, i) => {
    const v = values[i];
    const h = (v / max) * f.ih;
    const x = f.m.l + i * bw + bw * 0.2;
    const y = f.m.t + f.ih - h;
    const col = colors ? colors[i] : C.hold;
    s += `<rect class="bar" x="${x}" y="${y}" width="${bw * 0.6}" height="${Math.max(h, 0)}"
            fill="${col}" rx="2"><title>${l}: ${fmt(v)}</title></rect>`;
    s += `<text x="${x + bw * 0.3}" y="${y - 6}" text-anchor="middle"
            font-size="11.5" font-weight="500" fill="${C.ink}">${fmt(v)}</text>`;
    s += `<text x="${x + bw * 0.3}" y="${f.m.t + f.ih + 18}" text-anchor="middle"
            font-size="12" fill="${C.mute}">${l}</text>`;
  });
  if (note) s += `<text x="${f.m.l}" y="${f.h - 4}" font-size="11" fill="${C.mute}">${note}</text>`;
  node.innerHTML = s + '</svg>';
}

function lineChart(node, { labels, values, counts, fmt = fmtPct }) {
  const f = frame(node, 250);
  const max = Math.max(...values, 1e-9) * 1.2;
  const step = f.iw / Math.max(labels.length - 1, 1);
  const pt = i => [f.m.l + i * step, f.m.t + f.ih - (values[i] / max) * f.ih];
  let s = `<svg viewBox="0 0 ${f.w} ${f.h}" width="100%" height="${f.h}" role="img">`;
  s += axis(f, scale(max), fmt);
  const pts = labels.map((_, i) => pt(i));
  s += `<path d="M${f.m.l},${f.m.t + f.ih} L${pts.map(p => p.join(',')).join(' L')}
         L${f.m.l + f.iw},${f.m.t + f.ih}Z" fill="${C.risk}" opacity=".08"/>`;
  s += `<polyline points="${pts.map(p => p.join(',')).join(' ')}" fill="none"
         stroke="${C.risk}" stroke-width="2" stroke-linejoin="round"/>`;
  pts.forEach((p, i) => {
    s += `<circle class="dot" cx="${p[0]}" cy="${p[1]}" r="4" fill="${C.risk}">
            <title>${labels[i]} days — ${fmt(values[i])} (${fmtInt(counts[i])} accounts)</title>
          </circle>`;
    s += `<text x="${p[0]}" y="${p[1] - 11}" text-anchor="middle" font-size="11"
            font-weight="500" fill="${C.ink}">${fmt(values[i])}</text>`;
    s += `<text x="${p[0]}" y="${f.m.t + f.ih + 18}" text-anchor="middle" font-size="12"
            fill="${C.mute}">${labels[i]}</text>`;
  });
  node.innerHTML = s + '</svg>';
}

function hbarChart(node, { labels, values }) {
  const rowH = 26, h = labels.length * rowH + 30;
  const w = Math.max(node.clientWidth || 520, 260);
  const lw = 168, iw = w - lw - 60;
  const max = Math.max(...values, 1e-9);
  let s = `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img">`;
  labels.forEach((l, i) => {
    const y = 14 + i * rowH;
    const bw = (values[i] / max) * iw;
    s += `<text x="${lw - 10}" y="${y + 12}" text-anchor="end" font-size="12"
            fill="${C.ink}">${l}</text>`;
    s += `<rect class="bar" x="${lw}" y="${y + 2}" width="${bw}" height="15"
            fill="${C.hold}" rx="2"><title>${l}: ${values[i].toFixed(4)}</title></rect>`;
    s += `<text x="${lw + bw + 7}" y="${y + 14}" font-size="11"
            fill="${C.mute}">${values[i].toFixed(3)}</text>`;
  });
  node.innerHTML = s + '</svg>';
}

/* ---------- state ------------------------------------------------------- */

const COL = {};
let STATE = { plan: null, region: null, contract: null, dorm: 14, risk: 0.30 };

function init() {
  CUBE.columns.forEach((c, i) => COL[c] = i);
  buildFilters();
  bindControls();
  render();
  let t; addEventListener('resize', () => { clearTimeout(t); t = setTimeout(render, 140); });
}

function rows() {
  return CUBE.rows.filter(r =>
    (STATE.plan === null || r[COL.plan] === STATE.plan) &&
    (STATE.region === null || r[COL.region] === STATE.region) &&
    (STATE.contract === null || r[COL.contract] === STATE.contract));
}

/* ---------- filters ----------------------------------------------------- */

function chipRow(name, levels) {
  const mk = (label, val) =>
    `<button class="chip" role="radio" data-dim="${name}" data-val="${val}"
       aria-checked="false">${label}</button>`;
  return `<div class="filter"><div class="flabel">${name}</div>
      <div class="chips" role="radiogroup" aria-label="${name}">
      ${mk('All', '')}${levels.map((l, i) => mk(l, i)).join('')}</div></div>`;
}

function buildFilters() {
  el('filters').innerHTML =
    chipRow('plan', CUBE.plans) +
    chipRow('region', CUBE.regions) +
    chipRow('contract', CUBE.contracts);
  document.querySelectorAll('.chip').forEach(b => {
    b.addEventListener('click', () => {
      const dim = b.dataset.dim;
      STATE[dim] = b.dataset.val === '' ? null : +b.dataset.val;
      render();
    });
  });
}

function syncChips() {
  document.querySelectorAll('.chip').forEach(b => {
    const cur = STATE[b.dataset.dim];
    const on = (b.dataset.val === '' && cur === null) || (+b.dataset.val === cur);
    b.classList.toggle('on', on);
    b.setAttribute('aria-checked', on ? 'true' : 'false');
  });
}

function bindControls() {
  el('dorm').addEventListener('input', e => { STATE.dorm = +e.target.value; render(); });
  el('risk').addEventListener('input', e => { STATE.risk = +e.target.value / 100; render(); });
  el('reset').addEventListener('click', () => {
    STATE = { plan: null, region: null, contract: null, dorm: 14, risk: 30 / 100 };
    el('dorm').value = 14; el('risk').value = 30; render();
  });
}

/* ---------- render ------------------------------------------------------ */

function render() {
  const R = rows();
  syncChips();
  el('scope').textContent = scopeSentence(R.length);

  if (!R.length) {
    el('empty').hidden = false;
    ['kpis', 'grid', 'sim', 'tablewrap'].forEach(i => el(i).hidden = true);
    return;
  }
  el('empty').hidden = true;
  ['kpis', 'grid', 'sim', 'tablewrap'].forEach(i => el(i).hidden = false);

  renderKpis(R);
  renderPlan(R);
  renderDormancy(R);
  hbarChart(el('c-drivers'), { labels: CUBE.drivers.map(d => d[0]),
                               values: CUBE.drivers.map(d => d[1]) });
  renderSim(R);
  renderTable(R);
}

function scopeSentence(n) {
  const bits = [];
  if (STATE.plan !== null) bits.push(CUBE.plans[STATE.plan]);
  if (STATE.contract !== null) bits.push(CUBE.contracts[STATE.contract]);
  const where = STATE.region === null ? 'all regions' : CUBE.regions[STATE.region];
  return `${fmtInt(n)} ${bits.join(' ') || ''} accounts in ${where}`.replace(/\s+/g, ' ');
}

function renderKpis(R) {
  const churn = R.reduce((a, r) => a + r[COL.churned], 0);
  const mrr = R.reduce((a, r) => a + r[COL.mrr], 0);
  const lost = R.filter(r => r[COL.churned]).reduce((a, r) => a + r[COL.mrr], 0);
  const cards = [
    ['Churn rate', fmtPct(churn / R.length), `${fmtInt(churn)} of ${fmtInt(R.length)} accounts`],
    ['Monthly revenue', fmtUsd(mrr), 'in the current selection'],
    ['MRR lost to churn', fmtUsd(lost), `${fmtPct(lost / mrr)} of selected revenue`],
    ['Median MRR', fmtUsd(median(R.map(r => r[COL.mrr]))), 'per account'],
  ];
  el('kpis').innerHTML = cards.map(([l, v, c]) =>
    `<div class="kpi"><span class="v">${v}</span><div class="l">${l}</div>
     <div class="c">${c}</div></div>`).join('');
}

function median(a) { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)] || 0; }

function renderPlan(R) {
  const by = CUBE.plans.map((_, i) => {
    const g = R.filter(r => r[COL.plan] === i);
    return { n: g.length, rate: g.length ? g.reduce((a, r) => a + r[COL.churned], 0) / g.length : 0 };
  });
  const keep = CUBE.plans.map((p, i) => i).filter(i => by[i].n > 0);
  barChart(el('c-plan'), {
    labels: keep.map(i => `${CUBE.plans[i]}\u2009(${fmtInt(by[i].n)})`.replace(/\u2009/, ' ')),
    values: keep.map(i => by[i].rate),
    colors: keep.map(i => by[i].rate > 0.15 ? C.risk : by[i].rate > 0.06 ? C.watch : C.hold),
  });
}

const DORM_BINS = [[0, 7, '0–7'], [8, 14, '8–14'], [15, 30, '15–30'],
                   [31, 60, '31–60'], [61, 9999, '60+']];

function renderDormancy(R) {
  const labels = [], values = [], counts = [];
  DORM_BINS.forEach(([lo, hi, lab]) => {
    const g = R.filter(r => r[COL.dorm] >= lo && r[COL.dorm] <= hi);
    if (!g.length) return;
    labels.push(lab); counts.push(g.length);
    values.push(g.reduce((a, r) => a + r[COL.churned], 0) / g.length);
  });
  lineChart(el('c-dorm'), { labels, values, counts });
}

/* the interactive centrepiece: who would this week's outreach list contain? */
function renderSim(R) {
  const flagged = R.filter(r => r[COL.dorm] >= STATE.dorm && r[COL.risk] >= STATE.risk);
  const churners = R.reduce((a, r) => a + r[COL.churned], 0);
  const caught = flagged.reduce((a, r) => a + r[COL.churned], 0);
  const mrrCovered = flagged.reduce((a, r) => a + r[COL.mrr], 0);
  const precision = flagged.length ? caught / flagged.length : 0;

  el('dorm-out').textContent = STATE.dorm + ' days';
  el('risk-out').textContent = Math.round(STATE.risk * 100) + '%';
  el('sim-out').innerHTML = [
    ['Accounts flagged', fmtInt(flagged.length),
     `${fmtPct(flagged.length / R.length)} of the selection`],
    ['Churners captured', fmtPct(churners ? caught / churners : 0),
     `${fmtInt(caught)} of ${fmtInt(churners)}`],
    ['Hit rate', fmtPct(precision),
     'share of flagged accounts that actually churned'],
    ['MRR covered', fmtUsd(mrrCovered), 'monthly revenue in the flagged list'],
  ].map(([l, v, c]) =>
    `<div class="simcell"><span class="v">${v}</span><div class="l">${l}</div>
     <div class="c">${c}</div></div>`).join('');
}

function renderTable(R) {
  const top = [...R].sort((a, b) => b[COL.risk] - a[COL.risk]).slice(0, 12);
  el('table').innerHTML =
    `<thead><tr><th>Account</th><th>Plan</th><th>Region</th>
       <th class="n">MRR</th><th class="n">Quiet for</th>
       <th class="n">Risk</th><th>Outcome</th></tr></thead><tbody>` +
    top.map(r => `<tr>
      <td class="mono">${CUBE.ids[r[COL.id]]}</td>
      <td>${CUBE.plans[r[COL.plan]]}</td>
      <td>${CUBE.regions[r[COL.region]]}</td>
      <td class="n">${fmtUsd(r[COL.mrr])}</td>
      <td class="n">${r[COL.dorm]} d</td>
      <td class="n"><span class="pill" style="--f:${r[COL.risk]}">${fmtPct(r[COL.risk])}</span></td>
      <td>${r[COL.churned] ? '<span class="tag churned">churned</span>'
                           : '<span class="tag active">active</span>'}</td>
    </tr>`).join('') + '</tbody>';
}

document.addEventListener('DOMContentLoaded', init);
