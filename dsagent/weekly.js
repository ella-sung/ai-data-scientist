/* Weekly operating report for a donation marketplace.
   No dependencies, no CDN, works offline. Everything recomputes from CUBE. */

const C = {
  up: '#14655F', down: '#A3324B', flat: '#66707A',
  ink: '#0F1A22', mute: '#66707A', rule: '#D6DAD5',
  line: '#1D4E6B', line2: '#A3324B', line3: '#9A6B12', bar: '#1D4E6B'
};

const el = id => document.getElementById(id);
const pct = (v, d = 1) => (v * 100).toFixed(d) + '%';
const bps = v => (v * 100).toFixed(2) + '%';
const int = v => Math.round(v).toLocaleString();
const usd = v => '$' + Math.round(v).toLocaleString();
const usd2 = v => '$' + v.toFixed(2);
const money = v => v >= 1e6 ? '$' + (v / 1e6).toFixed(2) + 'M'
                 : v >= 1e3 ? '$' + (v / 1e3).toFixed(0) + 'K' : usd(v);
const dt = s => new Date(s + 'T00:00:00').toLocaleDateString('en-US',
  { month: 'short', day: 'numeric', year: 'numeric' });

const M = {}, S = {};
const NEVER = 99999;   // matches the sentinel written by weekly.py
let ST = { week: 0, cat: null, reg: null, ch: null, metric: 'gdv' };

/* ---------- svg kit ------------------------------------------------------ */

function box(node, h) {
  const w = Math.max(node.clientWidth || 520, 280);
  return { w, h, l: 60, r: 14, t: 16, b: 34, iw: w - 74, ih: h - 50 };
}

function grid(f, max, fmt, min = 0) {
  let s = '';
  for (let i = 0; i <= 4; i++) {
    const y = f.t + f.ih - (i / 4) * f.ih;
    s += `<line x1="${f.l}" y1="${y}" x2="${f.l + f.iw}" y2="${y}" stroke="${C.rule}"/>`;
    s += `<text x="${f.l - 8}" y="${y + 4}" text-anchor="end" font-size="11"
           fill="${C.mute}">${fmt(min + (max - min) * i / 4)}</text>`;
  }
  return s;
}

function xLabels(f, labels, step) {
  const every = Math.ceil(labels.length / 7);
  let s = '';
  labels.forEach((l, i) => {
    if (i % every) return;
    s += `<text x="${f.l + i * step}" y="${f.t + f.ih + 18}" text-anchor="middle"
           font-size="11" fill="${C.mute}">${l.slice(5).replace('-', '/')}</text>`;
  });
  return s;
}

function trendChart(node, { labels, values, fmt, marker }) {
  const f = box(node, 250);
  const max = Math.max(...values, 1e-9) * 1.15;
  const step = f.iw / Math.max(labels.length - 1, 1);
  const pts = values.map((v, i) => [f.l + i * step, f.t + f.ih - (v / max) * f.ih]);
  let s = `<svg viewBox="0 0 ${f.w} ${f.h}" width="100%" height="${f.h}" role="img">`;
  s += grid(f, max, fmt);
  s += `<path d="M${f.l},${f.t + f.ih} L${pts.map(p => p.join(',')).join(' L')} L${f.l + f.iw},${f.t + f.ih}Z"
         fill="${C.line}" opacity=".07"/>`;
  s += `<polyline points="${pts.map(p => p.join(',')).join(' ')}" fill="none"
         stroke="${C.line}" stroke-width="2" stroke-linejoin="round"/>`;
  if (pts[marker]) {
    s += `<line x1="${pts[marker][0]}" y1="${f.t}" x2="${pts[marker][0]}" y2="${f.t + f.ih}"
           stroke="${C.line2}" stroke-width="1" stroke-dasharray="3 3"/>`;
    s += `<circle cx="${pts[marker][0]}" cy="${pts[marker][1]}" r="5" fill="${C.line2}"/>`;
  }
  pts.forEach((p, i) => {
    s += `<circle cx="${p[0]}" cy="${p[1]}" r="9" fill="transparent" style="cursor:pointer"
           onclick="jumpWeek(${i})"><title>${dt(labels[i])} — ${fmt(values[i])}</title></circle>`;
  });
  node.innerHTML = s + xLabels(f, labels, step) + '</svg>';
}

/* take-rate decomposition: two components plus the total */
function stackChart(node, { labels, tips, proc, marker }) {
  const f = box(node, 250);
  const totals = tips.map((v, i) => v + proc[i]);
  const max = Math.max(...totals) * 1.2;
  const step = f.iw / Math.max(labels.length - 1, 1);
  const Y = v => f.t + f.ih - (v / max) * f.ih;
  let s = `<svg viewBox="0 0 ${f.w} ${f.h}" width="100%" height="${f.h}" role="img">`;
  s += grid(f, max, v => (v * 100).toFixed(1) + '%');
  const area = (top, bottom, fill, op) => {
    const up = top.map((v, i) => [f.l + i * step, Y(v)]);
    const dn = bottom.map((v, i) => [f.l + i * step, Y(v)]).reverse();
    return `<path d="M${up.map(p => p.join(',')).join(' L')} L${dn.map(p => p.join(',')).join(' L')}Z"
             fill="${fill}" opacity="${op}"/>`;
  };
  const zero = labels.map(() => 0);
  s += area(tips, zero, C.line, 0.5);
  s += area(totals, tips, C.line3, 0.45);
  s += `<polyline points="${totals.map((v, i) => [f.l + i * step, Y(v)].join(',')).join(' ')}"
         fill="none" stroke="${C.line2}" stroke-width="2"/>`;
  if (labels[marker]) {
    s += `<line x1="${f.l + marker * step}" y1="${f.t}" x2="${f.l + marker * step}"
           y2="${f.t + f.ih}" stroke="${C.ink}" stroke-width="1" stroke-dasharray="3 3"/>`;
  }
  labels.forEach((l, i) => {
    s += `<circle cx="${f.l + i * step}" cy="${Y(totals[i])}" r="9" fill="transparent"
           style="cursor:pointer" onclick="jumpWeek(${i})"><title>${dt(l)} — total ${bps(totals[i])}
 (tips ${bps(tips[i])}, processing ${bps(proc[i])})</title></circle>`;
  });
  node.innerHTML = s + xLabels(f, labels, step) + '</svg>';
  el('take-legend').innerHTML =
    `<span class="lg"><i style="background:${C.line};opacity:.5"></i>Donor tips</span>
     <span class="lg"><i style="background:${C.line3};opacity:.45"></i>Processing margin</span>
     <span class="lg"><i style="background:${C.line2}"></i>Total take rate</span>`;
}

function groupedBars(node, { labels, seriesA, seriesB, nameA, nameB, fmt }) {
  const f = box(node, 250);
  const max = Math.max(...seriesA, ...seriesB, 1e-9) * 1.25;
  const gw = f.iw / labels.length;
  let s = `<svg viewBox="0 0 ${f.w} ${f.h}" width="100%" height="${f.h}" role="img">`;
  s += grid(f, max, fmt);
  labels.forEach((l, i) => {
    const x = f.l + i * gw + gw * 0.16;
    const bw = gw * 0.31;
    [[seriesA[i], C.bar, nameA], [seriesB[i], C.line2, nameB]].forEach((d, k) => {
      const h = (d[0] / max) * f.ih;
      s += `<rect class="bar" x="${x + k * bw}" y="${f.t + f.ih - h}" width="${bw * 0.86}"
             height="${Math.max(h, 0)}" fill="${d[1]}" rx="2">
             <title>${l} — ${d[2]}: ${fmt(d[0])}</title></rect>`;
    });
    s += `<text x="${x + bw}" y="${f.t + f.ih + 18}" text-anchor="middle" font-size="10.5"
           fill="${C.mute}">${l.split(' ')[0].slice(0, 11)}</text>`;
  });
  node.innerHTML = s + '</svg>';
  el('trust-legend').innerHTML =
    `<span class="lg"><i style="background:${C.bar}"></i>${nameA}</span>
     <span class="lg"><i style="background:${C.line2}"></i>${nameB}</span>`;
}

function curveChart(node, { series, fmt }) {
  const f = box(node, 260);
  const n = series[0].values.length;
  const step = f.iw / Math.max(n - 1, 1);
  const palette = ['#1D4E6B', '#14655F', '#A3324B', '#9A6B12', '#5B4B8A'];
  let s = `<svg viewBox="0 0 ${f.w} ${f.h}" width="100%" height="${f.h}" role="img">`;
  s += grid(f, 1, fmt);
  series.forEach((ser, k) => {
    const pts = ser.values.map((v, i) => [f.l + i * step, f.t + f.ih - v * f.ih]);
    s += `<polyline points="${pts.map(p => p.join(',')).join(' ')}" fill="none"
           stroke="${palette[k % 5]}" stroke-width="2" stroke-linejoin="round"/>`;
    const last = pts[pts.length - 1];
    s += `<circle cx="${last[0]}" cy="${last[1]}" r="3.5" fill="${palette[k % 5]}">
           <title>${ser.name}: ${fmt(ser.values[n - 1])} at week ${n - 1}</title></circle>`;
  });
  for (let i = 0; i < n; i += Math.ceil(n / 6))
    s += `<text x="${f.l + i * step}" y="${f.t + f.ih + 18}" text-anchor="middle"
           font-size="11" fill="${C.mute}">w${i}</text>`;
  node.innerHTML = s + '</svg>';
  el('curve-legend').innerHTML = series.map((ser, k) =>
    `<span class="lg"><i style="background:${palette[k % 5]}"></i>${ser.name}</span>`).join('');
}

/* ---------- data --------------------------------------------------------- */

function mkRows(w) {
  return CUBE.rows.filter(r => r[M.w] === w &&
    (ST.cat === null || r[M.cat] === ST.cat) &&
    (ST.reg === null || r[M.reg] === ST.reg) &&
    (ST.ch === null || r[M.ch] === ST.ch));
}

const SUMS = ['camp', 'funded', 'fast', 'goal', 'gdv', 'don', 'donors', 'retdon',
              'fromdon', 'repeatorg', 'tips', 'procrev', 'proccost', 'rev',
              'refunds', 'refamt', 'cb', 'fraud', 'spend'];

function agg(rows) {
  const a = {};
  SUMS.forEach(k => a[k] = 0);
  a.paidCamp = 0; a.paidSpend = 0; a.payWeighted = 0;
  rows.forEach(r => {
    SUMS.forEach(k => a[k] += r[M[k]]);
    a.payWeighted += r[M.paydays] * r[M.camp];
    if (r[M.paid]) { a.paidCamp += r[M.camp]; a.paidSpend += r[M.spend]; }
  });
  a.takeRate = a.gdv ? a.rev / a.gdv : 0;
  a.tipRate = a.gdv ? a.tips / a.gdv : 0;
  a.procRate = a.gdv ? (a.procrev - a.proccost) / a.gdv : 0;
  a.avgDonation = a.don ? a.gdv / a.don : 0;
  a.fundedRate = a.camp ? a.funded / a.camp : 0;
  a.attainment = a.goal ? a.gdv / a.goal : 0;
  a.fastRate = a.camp ? a.fast / a.camp : 0;
  a.donPerCamp = a.camp ? a.don / a.camp : 0;
  a.repeatDonor = a.donors ? a.retdon / a.donors : 0;
  a.viralShare = a.camp ? a.fromdon / a.camp : 0;
  a.repeatOrg = a.camp ? a.repeatorg / a.camp : 0;
  a.paidShare = a.camp ? a.paidCamp / a.camp : 0;
  a.paidCac = a.paidCamp ? a.paidSpend / a.paidCamp : 0;
  a.refundRate = a.gdv ? a.refamt / a.gdv : 0;
  a.cbRate = a.don ? a.cb / a.don : 0;
  a.fraudRate = a.camp ? a.fraud / a.camp : 0;
  a.payoutDays = a.camp ? a.payWeighted / a.camp : 0;
  return a;
}

const subRows = () => CUBE.sub.rows.filter(r => ST.reg === null || r[S.reg] === ST.reg);

/* ---------- boot --------------------------------------------------------- */

function init() {
  CUBE.cols.forEach((c, i) => M[c] = i);
  CUBE.sub.cols.forEach((c, i) => S[c] = i);
  ST.week = CUBE.weeks.length - 1;
  el('filters').innerHTML =
    chipRow('cat', 'Category', CUBE.categories) +
    chipRow('reg', 'Region', CUBE.regions) +
    chipRow('ch', 'Channel', CUBE.channels);
  document.querySelectorAll('#filters .chip').forEach(b =>
    b.addEventListener('click', () => {
      ST[b.dataset.dim] = b.dataset.val === '' ? null : +b.dataset.val; render(); }));
  document.querySelectorAll('#metric .chip').forEach(b =>
    b.addEventListener('click', () => { ST.metric = b.dataset.metric; render(); }));
  el('prev').addEventListener('click', () => { if (ST.week > 0) { ST.week--; render(); } });
  el('next').addEventListener('click', () => {
    if (ST.week < CUBE.weeks.length - 1) { ST.week++; render(); } });
  el('reset').addEventListener('click', () => {
    ST = { week: CUBE.weeks.length - 1, cat: null, reg: null, ch: null, metric: ST.metric };
    render(); });
  render();
  let t; addEventListener('resize', () => { clearTimeout(t); t = setTimeout(render, 140); });
}

function chipRow(dim, label, levels) {
  const b = (t, v) => `<button class="chip" data-dim="${dim}" data-val="${v}">${t}</button>`;
  return `<div class="filter"><div class="flabel">${label}</div><div class="chips">
    ${b('All', '')}${levels.map((l, i) => b(l, i)).join('')}</div></div>`;
}

function jumpWeek(i) { ST.week = i; render(); }

/* ---------- render ------------------------------------------------------- */

function render() {
  syncChips();
  const w = ST.week;
  el('weeklabel').textContent = 'Week of ' + dt(CUBE.weeks[w]);
  el('prev').disabled = w === 0;
  el('next').disabled = w === CUBE.weeks.length - 1;
  el('scope').textContent = scopeText();

  const cur = agg(mkRows(w));
  if (!cur.camp) {
    el('empty').hidden = false;
    ['kpi-scale', 'kpi-liq', 'kpi-loop', 'kpi-trust', 'kpi-sub', 'panels',
     'segwrap', 'movers'].forEach(i => el(i).hidden = true);
    return;
  }
  el('empty').hidden = true;
  ['kpi-scale', 'kpi-liq', 'kpi-loop', 'kpi-trust', 'kpi-sub', 'panels',
   'segwrap', 'movers'].forEach(i => el(i).hidden = false);

  const prv = w > 0 ? agg(mkRows(w - 1)) : null;
  const base = trailing(w, 4);
  renderBands(cur, prv, base);
  renderSubscription();
  renderTrend();
  renderTakeRate();
  renderTrust(w);
  renderCurves();
  renderSegments(w);
  renderMovers(w);
}

function trailing(w, k) {
  const start = Math.max(0, w - k);
  if (start === w) return null;
  const acc = {};
  ['gdv', 'rev', 'camp', 'don'].forEach(x => acc[x] = 0);
  for (let i = start; i < w; i++) {
    const a = agg(mkRows(i));
    acc.gdv += a.gdv; acc.rev += a.rev; acc.camp += a.camp; acc.don += a.don;
  }
  const n = w - start;
  return { gdv: acc.gdv / n, rev: acc.rev / n, camp: acc.camp / n, don: acc.don / n };
}

function scopeText() {
  const p = [];
  if (ST.cat !== null) p.push(CUBE.categories[ST.cat]);
  if (ST.ch !== null) p.push(CUBE.channels[ST.ch]);
  return (p.join(' · ') || 'all categories') + ' in ' +
         (ST.reg === null ? 'all regions' : CUBE.regions[ST.reg]);
}

function syncChips() {
  document.querySelectorAll('#filters .chip').forEach(b => {
    const c = ST[b.dataset.dim];
    b.classList.toggle('on', (b.dataset.val === '' && c === null) || +b.dataset.val === c);
  });
  document.querySelectorAll('#metric .chip').forEach(b =>
    b.classList.toggle('on', b.dataset.metric === ST.metric));
}

function delta(cur, prev, invert) {
  if (prev == null || !prev) return '<span class="d flat">—</span>';
  const d = (cur - prev) / prev;
  const cls = Math.abs(d) < 0.005 ? 'flat' : (invert ? d < 0 : d > 0) ? 'up' : 'down';
  const arr = Math.abs(d) < 0.005 ? '' : d > 0 ? '▲' : '▼';
  return `<span class="d ${cls}">${arr} ${(Math.abs(d) * 100).toFixed(1)}%</span>`;
}

const kpi = (l, v, d, c) => `<div class="kpi"><span class="v">${v}</span>
  <div class="l">${l} ${d || ''}</div><div class="c">${c}</div></div>`;

function renderBands(c, p, b) {
  el('kpi-scale').innerHTML =
    kpi('Gross donation volume', money(c.gdv), delta(c.gdv, p && p.gdv),
        b ? `4-wk avg ${money(b.gdv)}` : 'no prior weeks') +
    kpi('Net revenue', money(c.rev), delta(c.rev, p && p.rev),
        'tips plus processing, net of network cost') +
    kpi('Take rate', bps(c.takeRate), delta(c.takeRate, p && p.takeRate),
        `tips ${bps(c.tipRate)} · processing ${bps(c.procRate)}`) +
    kpi('Donations', int(c.don), delta(c.don, p && p.don),
        `${int(c.donors)} unique donors`) +
    kpi('Average donation', usd2(c.avgDonation), delta(c.avgDonation, p && p.avgDonation),
        'per individual gift') +
    kpi('Campaigns created', int(c.camp), delta(c.camp, p && p.camp),
        b ? `4-wk avg ${int(b.camp)}` : '');

  el('kpi-liq').innerHTML =
    kpi('Fully funded rate', pct(c.fundedRate), delta(c.fundedRate, p && p.fundedRate),
        'campaigns reaching 100% of goal') +
    kpi('Goal attainment', pct(c.attainment), delta(c.attainment, p && p.attainment),
        'raised as a share of goals set') +
    kpi('Funded within 24h', pct(c.fastRate), delta(c.fastRate, p && p.fastRate),
        'first donation on day one') +
    kpi('Donations per campaign', c.donPerCamp.toFixed(1),
        delta(c.donPerCamp, p && p.donPerCamp), 'depth of support');

  el('kpi-loop').innerHTML =
    kpi('Repeat donor rate', pct(c.repeatDonor), delta(c.repeatDonor, p && p.repeatDonor),
        'donors who had given before') +
    kpi('Organizers from donors', pct(c.viralShare), delta(c.viralShare, p && p.viralShare),
        'the flywheel: donor becomes organizer') +
    kpi('Repeat organizer rate', pct(c.repeatOrg), delta(c.repeatOrg, p && p.repeatOrg),
        'ran a campaign before') +
    kpi('Paid share of campaigns', pct(c.paidShare), delta(c.paidShare, p && p.paidShare, true),
        'the rest arrive organically') +
    kpi('CAC on paid channels', usd2(c.paidCac), delta(c.paidCac, p && p.paidCac, true),
        'blended CAC would hide this');

  el('kpi-trust').innerHTML =
    kpi('Refund rate', bps(c.refundRate), delta(c.refundRate, p && p.refundRate, true),
        `${money(c.refamt)} refunded`) +
    kpi('Chargeback rate', (c.cbRate * 100).toFixed(3) + '%',
        delta(c.cbRate, p && p.cbRate, true), `${int(c.cb)} disputes`) +
    kpi('Campaigns flagged for fraud', (c.fraudRate * 100).toFixed(3) + '%',
        delta(c.fraudRate, p && p.fraudRate, true), `${int(c.fraud)} campaigns`) +
    kpi('Average payout time', c.payoutDays.toFixed(1) + ' days',
        delta(c.payoutDays, p && p.payoutDays, true), 'campaign close to funds available');
}

function renderSubscription() {
  const rows = subRows();
  const active = rows.filter(r => r[S.active] === 1);
  const mrr = active.reduce((a, r) => a + r[S.mrr], 0);
  // Alive at week 0: signed up before the window, and either never churned or
  // churned inside it. Including accounts that churned earlier would drag NRR
  // down by counting revenue that was already gone before the window opened.
  const cohort = rows.filter(r => r[S.signup] < 0 &&
    (r[S.churn] === NEVER || r[S.churn] >= 0));
  const startMrr = cohort.reduce((a, r) => a + r[S.prior], 0);
  const endMrr = cohort.filter(r => r[S.active] === 1)
                       .reduce((a, r) => a + r[S.mrr], 0);
  const grrMrr = cohort.filter(r => r[S.active] === 1)
                       .reduce((a, r) => a + Math.min(r[S.mrr], r[S.prior]), 0);
  const nrr = startMrr ? endMrr / startMrr : 0;
  const grr = startMrr ? grrMrr / startMrr : 0;
  const logo = cohort.length
    ? cohort.filter(r => r[S.active] === 1).length / cohort.length : 0;
  const arpa = active.length ? mrr / active.length : 0;
  const avgCac = rows.length ? rows.reduce((a, r) => a + r[S.cac], 0) / rows.length : 0;
  const churned = rows.filter(r => r[S.active] === 0);
  const tenM = churned.length
    ? churned.reduce((a, r) => a + r[S.tenure], 0) / churned.length / 4.33 : 0;
  const ltv = arpa * 0.78 * tenM;

  el('kpi-sub').innerHTML =
    kpi('Subscription ARR', money(mrr * 12), '', `${int(active.length)} active accounts`) +
    kpi('Net revenue retention', pct(nrr), '', 'expansion net of churn, prior cohort') +
    kpi('Gross revenue retention', pct(grr), '', 'ignoring expansion') +
    kpi('Logo retention', pct(logo), '', 'accounts still subscribed') +
    kpi('CAC payback', (avgCac / (arpa * 0.78)).toFixed(1) + ' mo', '',
        `LTV : CAC ${(ltv / avgCac).toFixed(1)}×`);
}

const METRICS = {
  gdv: { label: 'Gross donation volume', fmt: money, get: a => a.gdv },
  rev: { label: 'Net revenue', fmt: money, get: a => a.rev },
  take: { label: 'Take rate', fmt: v => (v * 100).toFixed(2) + '%', get: a => a.takeRate },
  avgDonation: { label: 'Average donation', fmt: usd2, get: a => a.avgDonation },
  fundedRate: { label: 'Fully funded rate', fmt: v => pct(v), get: a => a.fundedRate },
  repeatDonor: { label: 'Repeat donor rate', fmt: v => pct(v), get: a => a.repeatDonor },
  paidCac: { label: 'CAC on paid channels', fmt: usd2, get: a => a.paidCac },
};

function renderTrend() {
  const m = METRICS[ST.metric] || METRICS.gdv;
  const values = CUBE.weeks.map((_, i) => m.get(agg(mkRows(i))));
  el('trend-title').textContent = m.label + ' by week';
  trendChart(el('c-trend'), { labels: CUBE.weeks, values, fmt: m.fmt, marker: ST.week });
}

function renderTakeRate() {
  const tips = [], proc = [];
  CUBE.weeks.forEach((_, i) => {
    const a = agg(mkRows(i)); tips.push(a.tipRate); proc.push(a.procRate);
  });
  stackChart(el('c-take'), { labels: CUBE.weeks, tips, proc, marker: ST.week });
}

function renderTrust(w) {
  const rows = mkRows(w);
  const labels = [], refund = [], fraud = [];
  CUBE.categories.forEach((name, i) => {
    const a = agg(rows.filter(r => r[M.cat] === i));
    if (!a.camp) return;
    labels.push(name); refund.push(a.refundRate); fraud.push(a.fraudRate);
  });
  groupedBars(el('c-trust'), {
    labels, seriesA: refund, seriesB: fraud,
    nameA: 'Refund rate', nameB: 'Fraud-flagged rate',
    fmt: v => (v * 100).toFixed(2) + '%',
  });
}

function renderCurves() {
  const rows = subRows();
  const N = CUBE.weeks.length - 1, H = 52;
  const series = CUBE.sub.channels.map((name, ci) => {
    const g = rows.filter(r => r[S.ch] === ci);
    const values = [];
    for (let t = 0; t <= H; t++) {
      const atRisk = g.filter(r => N - r[S.signup] >= t);
      values.push(atRisk.length
        ? atRisk.filter(r => r[S.tenure] >= t).length / atRisk.length
        : (values[values.length - 1] ?? 1));
    }
    return { name, values };
  });
  curveChart(el('c-curve'), { series, fmt: v => pct(v, 0) });
}

function renderSegments(w) {
  const rows = mkRows(w), prev = w > 0 ? mkRows(w - 1) : [];
  const segs = CUBE.categories.map((name, i) => {
    const a = agg(rows.filter(r => r[M.cat] === i));
    const p = w > 0 ? agg(prev.filter(r => r[M.cat] === i)) : null;
    return { name, a, p };
  }).filter(s => s.a.camp > 0).sort((x, y) => y.a.gdv - x.a.gdv);
  const total = segs.reduce((t, s) => t + s.a.gdv, 0);

  el('segtable').innerHTML =
    `<thead><tr><th>Category</th><th class="n">GDV</th><th class="n">Share</th>
      <th class="n">Take rate</th><th class="n">Avg donation</th>
      <th class="n">Fully funded</th><th class="n">Repeat donors</th>
      <th class="n">Refund rate</th><th class="n">WoW GDV</th></tr></thead><tbody>` +
    segs.map(({ name, a, p }) => `<tr>
      <td>${name}</td>
      <td class="n">${money(a.gdv)}</td>
      <td class="n"><span class="share" style="--f:${a.gdv / total}">${pct(a.gdv / total, 0)}</span></td>
      <td class="n">${bps(a.takeRate)}</td>
      <td class="n">${usd2(a.avgDonation)}</td>
      <td class="n">${pct(a.fundedRate)}</td>
      <td class="n">${pct(a.repeatDonor)}</td>
      <td class="n ${a.refundRate > 0.012 ? 'warn' : ''}">${bps(a.refundRate)}</td>
      <td class="n">${delta(a.gdv, p && p.gdv)}</td>
    </tr>`).join('') + '</tbody>';
}

// A rate computed on a small numerator swings wildly week to week and will
// crowd out every real movement. Each watched metric therefore declares the
// minimum count its denominator or numerator must reach to be reportable.
const WATCH = [
  { key: 'gdv', dim: 'cat', label: 'GDV', fmt: money, guard: a => a.camp >= 300 },
  { key: 'takeRate', dim: 'cat', label: 'take rate', fmt: bps, guard: a => a.gdv >= 2e6 },
  { key: 'refundRate', dim: 'cat', label: 'refund rate', fmt: bps, invert: true,
    guard: a => a.refunds >= 250 },
  { key: 'fraudRate', dim: 'cat', label: 'fraud rate', invert: true,
    fmt: v => (v * 100).toFixed(3) + '%', guard: a => a.fraud >= 25 },
  { key: 'paidCac', dim: 'ch', label: 'paid CAC', fmt: usd2, invert: true,
    guard: a => a.paidCamp >= 400 },
];

function renderMovers(w) {
  if (w === 0) { el('movers').hidden = true; return; }
  const cur = mkRows(w), prv = mkRows(w - 1);
  const items = [];
  WATCH.forEach(spec => {
    const levels = spec.dim === 'cat' ? CUBE.categories : CUBE.channels;
    levels.forEach((name, i) => {
      const idx = spec.dim === 'cat' ? M.cat : M.ch;
      const a = agg(cur.filter(r => r[idx] === i));
      const b = agg(prv.filter(r => r[idx] === i));
      if (!b[spec.key] || !spec.guard(a) || !spec.guard(b)) return;
      items.push({ name, label: spec.label, invert: spec.invert, fmt: spec.fmt,
                   now: a[spec.key], d: (a[spec.key] - b[spec.key]) / b[spec.key] });
    });
  });
  items.sort((a, b) => Math.abs(b.d) - Math.abs(a.d));
  el('mover-list').innerHTML = items.slice(0, 7).map(m => {
    const bad = m.invert ? m.d > 0 : m.d < 0;
    return `<li class="${bad ? 'bad' : 'good'}">
      <span class="mn">${m.name}</span><span class="mk">${m.label}</span>
      <span class="md">${m.d > 0 ? '+' : ''}${(m.d * 100).toFixed(1)}%</span>
      <span class="mv">${m.fmt(m.now)}</span></li>`;
  }).join('');
}

document.addEventListener('DOMContentLoaded', init);
