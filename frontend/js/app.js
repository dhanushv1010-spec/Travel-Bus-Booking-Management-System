'use strict';
/* ---------- helpers */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const money = n => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
const pdt = s => new Date(String(s).replace(' ', 'T'));
const fdate = s => new Date(String(s).slice(0, 10) + 'T00:00').toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });
const hm = s => String(s).slice(11, 16);
const dur = m => `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`;
const localDay = (d = new Date()) => new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10);
const ROLES = { admin: 'Administrator', customer: 'Customer', manager: 'Bus manager' };

let PRESET = null;
let me = null, role = 'customer', registering = false, current = '';
const main = $('#main'), V = {}, ACT = {};

async function api(url, method = 'GET', body) {
  let r;
  try {
    r = await fetch(url, { method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
  } catch (e) {
    throw new Error("Can't reach the server. Start it with 'python app.py' and open http://localhost:5000");
  }
  let d = {};
  try { d = await r.json(); } catch (e) { /* empty body */ }
  if (!r.ok) {
    if (r.status === 401 && me) { me = null; showLogin(); }
    if (d.error) throw new Error(d.error);
    if (r.status === 404 || r.status === 405) throw new Error('This page is not running through the Flask server. Open http://localhost:5000 instead of opening the file or using Live Server.');
    throw new Error(`Server error (${r.status}). Check the terminal where app.py is running.`);
  }
  return d;
}
function toast(msg, bad) {
  const t = document.createElement('div');
  t.className = 'toast' + (bad ? ' bad' : '');
  t.textContent = msg;
  $('#toast').append(t);
  setTimeout(() => t.remove(), 4200);
}
const guard = fn => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, true); } };
function openModal(html, narrow) {
  const m = $('#modal');
  m.innerHTML = `<div class="sheet ${narrow ? 'narrow' : ''}" role="dialog" aria-modal="true"><button class="x" data-act="close" aria-label="Close">&times;</button>${html}</div>`;
  m.hidden = false;
}
function closeModal() { $('#modal').hidden = true; $('#modal').innerHTML = ''; }
const statusChip = b => b.status === 'CONFIRMED' ? '<span class="chip ok">Confirmed</span>' : '<span class="chip bad">Cancelled</span>';

/* ---------- sign in / out */
function showLogin() {
  $('#app').hidden = true; $('#login').hidden = false; closeModal();
  $('#loginForm').reset(); setMode(false); setPw(false);
}
function setPw(show) {
  const i = $('[name=password]'), b = $('#pwToggle');
  i.type = show ? 'text' : 'password';
  b.textContent = show ? 'Hide' : 'Show';
  b.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
  b.setAttribute('aria-pressed', show);
}
$('#pwToggle').onclick = () => setPw($('[name=password]').type === 'password');
function setMode(reg) {
  registering = reg;
  $('#regFields').hidden = !reg;
  $('#roles').hidden = reg;
  $('#formTitle').textContent = reg ? 'Create a customer account' : 'Sign in';
  $('#loginBtn').textContent = reg ? 'Create account' : 'Sign in';
  $('#switchLine').innerHTML = reg ? 'Already registered? <a href="#" id="switchLink">Sign in</a>' : 'New here? <a href="#" id="switchLink">Create a customer account</a>';
  $('#loginErr').hidden = true;
  setPw(false);
  $('[name=password]').autocomplete = reg ? 'new-password' : 'current-password';
}
document.addEventListener('click', e => {
  if (e.target.id === 'switchLink') { e.preventDefault(); setMode(!registering); }
  const rb = e.target.closest('#roles button');
  if (rb) { role = rb.dataset.role; $$('#roles button').forEach(b => b.setAttribute('aria-checked', b === rb)); }
});
$('#loginForm').onsubmit = async e => {
  e.preventDefault();
  const f = e.target, btn = $('#loginBtn'), err = $('#loginErr');
  err.hidden = true; btn.disabled = true;
  try {
    const d = registering
      ? await api('/api/register', 'POST', { name: f.elements.name.value, email: f.elements.email.value, username: f.username.value, password: f.password.value })
      : await api('/api/login', 'POST', { username: f.username.value, password: f.password.value, role });
    me = d; showApp();
  } catch (x) { err.textContent = x.message; err.hidden = false; }
  btn.disabled = false;
};
$('#logoutBtn').onclick = async () => { try { await api('/api/logout', 'POST'); } catch (e) { /* ignore */ } me = null; showLogin(); };
$('#menuBtn').onclick = () => $('.side').classList.toggle('open');

const NAV = {
  customer: [['search', 'Available buses'], ['routes', 'Routes'], ['tickets', 'My tickets']],
  manager: [['trips', 'My trips'], ['find', 'Find a ticket']],
  admin: [['overview', 'Overview'], ['trips', 'Trips'], ['network', 'Cities & routes'], ['buses', 'Buses'], ['people', 'People'], ['bookings', 'Bookings']]
};
function showApp() {
  $('#login').hidden = true; $('#app').hidden = false;
  $('#whoName').textContent = me.name; $('#whoRole').textContent = ROLES[me.role];
  $('#nav').innerHTML = NAV[me.role].map(([k, l]) => `<button data-nav="${k}">${l}</button>`).join('');
  go(NAV[me.role][0][0]);
}
async function go(view) {
  current = view;
  $('.side').classList.remove('open');
  $$('#nav button').forEach(b => b.classList.toggle('on', b.dataset.nav === view));
  $('#crumb').textContent = (NAV[me.role].find(n => n[0] === view) || [])[1] || '';
  main.innerHTML = '<p class="muted">Loading…</p>';
  try { await V[me.role + '.' + view](); } catch (e) { main.innerHTML = `<div class="panel err">${esc(e.message)}</div>`; }
}
document.addEventListener('click', e => {
  const n = e.target.closest('[data-nav]'); if (n) go(n.dataset.nav);
  const a = e.target.closest('[data-act]');
  if (a && ACT[a.dataset.act]) guard(ACT[a.dataset.act])(a, e);
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
ACT.close = () => closeModal();

/* ---------- tickets */
function ticket(b) {
  const gone = b.status !== 'CONFIRMED';
  return `<div class="ticket"><div class="tk-main">
    <div class="tk-top"><span>Wayfare</span><b>${esc(b.pnr)}</b></div>
    <h3>${esc(b.source)} to ${esc(b.dest)}</h3>
    <dl><div><dt>Passenger</dt><dd>${esc(b.passenger_name)}, ${b.age}</dd></div>
    <div><dt>Departs</dt><dd>${fdate(b.travel_date)}, ${esc(b.departure_time)}</dd></div>
    <div><dt>Bus</dt><dd>${esc(b.bus_name)}</dd></div>
    <div><dt>Class</dt><dd>${esc(b.seat_class)}</dd></div>
    <div><dt>Fare paid</dt><dd>${money(b.fare)}</dd></div>
    <div><dt>Status</dt><dd>${gone ? 'Cancelled' : 'Confirmed'}</dd></div></dl></div>
    <div class="tk-stub ${gone ? 'cx' : ''}"><small>Seat</small><b>${b.seat_no}</b><small>${esc(b.reg_no)}</small></div></div>`;
}
ACT.ticket = async el => {
  const b = await api('/api/lookup/' + encodeURIComponent(el.dataset.pnr));
  openModal(`<h2>Ticket</h2><p class="sub">Show the PNR when you board.</p>${ticket(b)}<div class="actions noprint"><button class="btn" onclick="window.print()">Print ticket</button></div>`, true);
};

function bookingsTable(rows, opts = {}) {
  if (!rows.length) return '<div class="empty">Nothing here yet.</div>';
  return `<div class="tablewrap"><table><thead><tr><th>PNR</th><th>Passenger</th><th>Trip</th><th>Departs</th><th>Seat</th><th class="num">Fare</th><th>Status</th><th></th></tr></thead><tbody>${rows.map(b => `
    <tr><td><b>${esc(b.pnr)}</b></td><td>${esc(b.passenger_name)}${opts.who ? `<br><small>by ${esc(b.booked_by)}</small>` : ''}</td>
    <td>${esc(b.source)} to ${esc(b.dest)}</td><td>${fdate(b.travel_date)}, ${esc(b.departure_time)}</td>
    <td>${b.seat_no} <small>${esc(b.seat_class)}</small></td>
    <td class="num">${money(b.fare)}${b.status === 'CANCELLED' ? `<br><small>refunded ${money(b.refund)}</small>` : ''}</td><td>${statusChip(b)}</td>
    <td><div class="actions"><button class="btn sm" data-act="ticket" data-pnr="${esc(b.pnr)}">View</button>
    ${opts.cancel && b.can_cancel ? `<button class="btn sm danger" data-act="cancel" data-id="${b.id}" data-pnr="${esc(b.pnr)}">Cancel</button>` : ''}</div></td></tr>`).join('')}</tbody></table></div>`;
}
function findBox() {
  return `<form class="panel row" id="findForm"><label>Find a ticket by PNR<input name="pnr" placeholder="WF12345678" required></label><button class="btn primary">Find ticket</button></form>`;
}
document.addEventListener('submit', e => {
  if (e.target.id === 'findForm') { e.preventDefault(); guard(ACT.ticket)({ dataset: { pnr: e.target.pnr.value } }); }
});

/* ======================= CUSTOMER ======================= */
V['customer.search'] = async () => {
  const cities = await api('/api/cities');
  const opt = '<option value="">Any city</option>' + cities.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
  const today = localDay();
  main.innerHTML = `<h1>Available buses</h1>
    <form id="sf" class="panel filters">
      <label>From<select name="from">${opt}</select></label>
      <label>To<select name="to">${opt}</select></label>
      <label>Date<input type="date" name="date" min="${today}" value="${today}" required></label>
      <label>Sort by<select name="sort"><option value="departure">Departure time</option><option value="fare">Lowest fare</option></select></label>
    </form><div class="days" id="days"></div><div id="res"></div>`;
  const f = $('#sf');
  if (PRESET) { f.elements.from.value = PRESET.from; f.elements.to.value = PRESET.to; PRESET = null; }

  const renderDays = () => {
    let h = '';
    for (let i = 0; i < 10; i++) {
      const d = new Date(); d.setDate(d.getDate() + i);
      const v = localDay(d), on = v === f.elements.date.value;
      h += `<button type="button" class="day ${on ? 'on' : ''}" data-d="${v}"><small>${i === 0 ? 'Today' : d.toLocaleDateString('en-IN', { weekday: 'short' })}</small><b>${d.getDate()}</b><small>${d.toLocaleDateString('en-IN', { month: 'short' })}</small></button>`;
    }
    $('#days').innerHTML = h;
  };
  const seatMap = t => {
    let g = '';
    for (let r = 0; r < t.total_seats / 4; r++) {
      let c = '';
      for (let k = 1; k <= 4; k++) {
        const n = r * 4 + k, kind = (k === 1 || k === 4) ? 'window' : 'aisle';
        c += t.booked_seats.includes(n)
          ? `<span class="mseat taken" title="Seat ${n} is taken">${n}</span>`
          : `<button type="button" class="mseat" title="Seat ${n}, ${kind}" data-act="book" data-id="${t.id}" data-seat="${n}">${n}</button>`;
      }
      g += `<div class="mgrp">${c}</div>`;
    }
    return `<div class="minimap"><div class="mini">${g}</div><small>${t.seats_left > 0 ? `${t.seats_left} of ${t.total_seats} seats free. Tap a free seat to book it.` : 'This bus is full. You can join the waitlist.'}</small></div>`;
  };
  const next = t => (t.arr.slice(0, 10) !== t.dep.slice(0, 10) ? '<sup>+1</sup>' : '');
  const card = t => `<article class="trip"><div class="tt"><span>${hm(t.dep)}</span><span class="dur">${dur(t.duration)}</span><span>${hm(t.arr)}${next(t)}</span></div>
    <div class="tm"><strong>${esc(t.source)} to ${esc(t.dest)}</strong><span class="muted">${esc(t.bus_name)} &middot; ${t.distance_km} km</span></div>
    <div>${t.seats_left > 0 ? `<span class="chip ok">${t.seats_left} seats left</span>` : '<span class="chip warn">Full, waitlist open</span>'}</div>
    <div class="tp"><small>from</small><b>${money(t.fare)}</b></div>
    <button class="btn primary" data-act="book" data-id="${t.id}">${t.seats_left > 0 ? 'Select seats' : 'Join waitlist'}</button>${seatMap(t)}</article>`;

  const run = guard(async () => {
    const res = $('#res'); res.innerHTML = '<p class="muted">Loading buses…</p>';
    const q = new URLSearchParams({ from: f.elements.from.value, to: f.elements.to.value, date: f.elements.date.value, sort: f.elements.sort.value });
    let d;
    try { d = await api('/api/search?' + q); } catch (x) { res.innerHTML = ''; throw x; }
    let h = '';
    if (d.direct.length) h += `<h3 class="group-title">${d.browse ? `${d.direct.length} bus${d.direct.length > 1 ? 'es' : ''} on ${fdate(f.elements.date.value)}` : 'Direct trips'}</h3>` + d.direct.map(card).join('');
    if (d.connecting.length) h += `<h3 class="group-title">With a change of bus</h3>` + d.connecting.map(c => `
      <div class="connect"><header><strong>${esc(c.legs[0].source)} to ${esc(c.legs[c.legs.length - 1].dest)} via ${c.via.map(esc).join(', ')}</strong>
      <span class="muted">${hm(c.dep)} to ${hm(c.arr)} &middot; ${dur(c.duration)} &middot; ${money(c.fare)} in total</span></header>
      ${c.legs.map(t => `<div class="leg"><span><b>${hm(t.dep)}</b> ${esc(t.source)} to ${esc(t.dest)} <small>${esc(t.bus_name)} &middot; ${money(t.fare)} &middot; ${t.seats_left} seats left</small></span>
      <button class="btn sm primary" data-act="book" data-id="${t.id}">${t.seats_left > 0 ? 'Choose seats' : 'Join waitlist'}</button></div>`).join('')}</div>`).join('');
    if (!h) h = `<div class="panel empty">${!d.has_route ? 'These cities are not connected by any route yet.' : d.next_date ? `No buses on this date. The next buses run on <b>${fdate(d.next_date)}</b>.<div style="margin-top:.8rem"><button class="btn primary" data-act="setDate" data-date="${d.next_date}">Show ${fdate(d.next_date)}</button></div>` : d.last_date ? `No buses on this date. Trips on this route are scheduled up to ${fdate(d.last_date)}. Ask a bus manager to add more.` : 'No buses are scheduled for this selection yet.'}</div>`;
    res.innerHTML = h;
  });
  f.onsubmit = e => { e.preventDefault(); renderDays(); run(); };
  f.onchange = () => { renderDays(); run(); };
  $('#days').onclick = e => {
    const b = e.target.closest('[data-d]');
    if (b) { f.elements.date.value = b.dataset.d; renderDays(); run(); }
  };
  renderDays();
  run();
};

ACT.setDate = el => { const f = $('#sf'); f.elements.date.value = el.dataset.date; f.requestSubmit(); };
ACT.routeSearch = el => { PRESET = { from: el.dataset.from, to: el.dataset.to }; go('search'); };
V['customer.routes'] = async () => {
  const rows = await api('/api/routes/overview');
  main.innerHTML = `<h1>Routes</h1><div class="panel"><div class="tablewrap"><table><thead><tr><th>Route</th><th class="num">Distance</th><th>Upcoming trips</th><th>Next departure</th><th></th></tr></thead><tbody>${rows.map(r => `<tr><td><b>${esc(r.source)} to ${esc(r.dest)}</b></td><td class="num">${r.distance_km} km</td><td>${r.trips ? r.trips : '<span class="muted">None</span>'}</td><td>${r.next ? `${fdate(r.next)}, ${hm(r.next)}` : '-'}</td><td><button class="btn sm primary" data-act="routeSearch" data-from="${r.source_id}" data-to="${r.dest_id}">Search trips</button></td></tr>`).join('')}</tbody></table></div></div>`;
};

/* booking dialog */
let BK = null;
ACT.book = async el => {
  const d = await api(`/api/trips/${el.dataset.id}/seats`);
  const pre = +el.dataset.seat || 0, ok1 = pre && !d.booked.includes(pre) && d.trip.total_seats - d.booked.length >= 1;
  BK = { trip: d.trip, booked: d.booked, cls: 'Economy', n: 1, manual: !!ok1, pref: 'any', sel: ok1 ? [pre] : [], pax: [{ name: me.name, age: '' }], tok: 0 };
  if (pre && !ok1) toast('That seat was just taken. Please pick another.', true);
  renderBK();
};
function renderBK() {
  const t = BK.trip, left = t.total_seats - BK.booked.length, wait = left < BK.n;
  while (BK.pax.length < BK.n) BK.pax.push({ name: '', age: '' });
  BK.pax.length = BK.n;
  if (wait) { BK.manual = false; BK.sel = []; }
  BK.sel = BK.sel.slice(0, BK.n);
  const rows = [];
  for (let r = 0; r < t.total_seats / 4; r++) {
    let cells = '';
    for (let c = 1; c <= 4; c++) {
      const n = r * 4 + c, taken = BK.booked.includes(n), sel = BK.sel.includes(n);
      cells += `<button type="button" class="seat ${taken ? 'taken' : ''} ${sel ? 'sel' : ''}" ${taken || !BK.manual ? 'disabled' : ''} data-act="seat" data-n="${n}" aria-label="Seat ${n}${taken ? ' taken' : ''}">${n}</button>`;
      if (c === 2) cells += '<i></i>';
    }
    rows.push(`<div class="srow">${cells}</div>`);
  }
  openModal(`<h2>${esc(t.source)} to ${esc(t.dest)}</h2>
    <p class="sub">${fdate(t.travel_date)}, ${hm(t.dep)} to ${hm(t.arr)} &middot; ${esc(t.bus_name)} &middot; ${left} of ${t.total_seats} seats free</p>
    <div class="two"><div>
      <label>Seat class</label>
      <div class="classes">${Object.entries(t.fares).map(([c, f]) => `<button type="button" class="${BK.cls === c ? 'on' : ''}" data-act="cls" data-c="${c}">${c}<b>${money(f)}</b></button>`).join('')}</div>
      <label>Passengers<select id="bkN">${[1, 2, 3, 4, 5, 6].map(i => `<option ${i === BK.n ? 'selected' : ''}>${i}</option>`).join('')}</select></label>
      <div style="margin-top:.8rem"><label>Names and ages</label>${BK.pax.map((p, i) => `<div class="pax"><input data-pax="${i}" data-f="name" placeholder="Full name" value="${esc(p.name)}"><input data-pax="${i}" data-f="age" type="number" min="1" max="120" placeholder="Age" value="${esc(p.age)}"></div>`).join('')}</div>
      ${wait ? `<div class="notice">Only ${left} seat${left === 1 ? '' : 's'} free. You'll be added to the waitlist and seated automatically if seats open up.</div>` : `
        <label class="check"><input type="checkbox" id="bkManual" ${BK.manual ? 'checked' : ''}> I'll choose my own seats</label>
        ${BK.manual ? '' : `<label>Seat preference<select id="bkPref">${[['any', 'Best available'], ['window', 'Window'], ['aisle', 'Aisle'], ['front', 'Near the front']].map(([v, l]) => `<option value="${v}" ${BK.pref === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label>`}`}
    </div><div>
      <div class="seatmap"><div class="front">Front of bus</div>${rows.join('')}</div>
      <div class="legend"><span>Free</span><span class="t">Taken</span><span class="s">Yours</span></div>
    </div></div>
    <div class="quote" id="quote">Calculating fare…</div>
    <button class="btn primary wide" data-act="confirm">${wait ? 'Join waitlist' : 'Confirm booking'}</button>`);
  loadQuote();
}
async function loadQuote() {
  const tok = ++BK.tok;
  try {
    const q = await api(`/api/trips/${BK.trip.id}/quote?cls=${BK.cls}&count=${BK.n}`);
    if (tok !== BK.tok || !$('#quote')) return;
    const p = q.per_seat;
    $('#quote').innerHTML = `<div><span>Distance charge</span><span>${money(p.distance_charge)}</span></div>
      <div><span>${BK.cls} surcharge</span><span>${money(p.class_surcharge)}</span></div>
      <div><span>Tax (5%)</span><span>${money(p.tax)}</span></div>
      <div><span>Fare per seat</span><span>${money(p.total)}</span></div>
      <div class="total"><span>Total for ${q.count} seat${q.count > 1 ? 's' : ''}</span><span>${money(q.total)}</span></div>`;
  } catch (e) { /* keep placeholder */ }
}
ACT.cls = el => { BK.cls = el.dataset.c; renderBK(); };
ACT.seat = el => {
  const n = +el.dataset.n, i = BK.sel.indexOf(n);
  if (i >= 0) BK.sel.splice(i, 1);
  else if (BK.sel.length < BK.n) BK.sel.push(n);
  else { toast(`You can pick ${BK.n} seat${BK.n > 1 ? 's' : ''}. Tap a chosen seat to release it.`, true); return; }
  renderBK();
};
document.addEventListener('change', e => {
  if (!BK || $('#modal').hidden) return;
  if (e.target.id === 'bkN') { BK.n = +e.target.value; renderBK(); }
  if (e.target.id === 'bkManual') { BK.manual = e.target.checked; BK.sel = []; renderBK(); }
  if (e.target.id === 'bkPref') BK.pref = e.target.value;
});
document.addEventListener('input', e => {
  const i = e.target.dataset && e.target.dataset.pax;
  if (BK && i !== undefined) BK.pax[+i][e.target.dataset.f] = e.target.value;
});
ACT.confirm = async el => {
  const left = BK.trip.total_seats - BK.booked.length;
  if (BK.pax.some(p => p.name.trim().length < 2 || !(+p.age >= 1 && +p.age <= 120))) throw new Error('Enter a name and a valid age for every passenger.');
  if (BK.manual && left >= BK.n && BK.sel.length !== BK.n) throw new Error(`Pick ${BK.n} seat${BK.n > 1 ? 's' : ''} on the map.`);
  el.disabled = true;
  try {
    const d = await api('/api/book', 'POST', { trip_id: BK.trip.id, seat_class: BK.cls, preference: BK.pref, passengers: BK.pax.map(p => ({ name: p.name.trim(), age: +p.age })), seats: BK.manual ? BK.sel : [] });
    if (d.waitlisted) { closeModal(); toast(d.message); go('tickets'); return; }
    openModal(`<h2>You're booked</h2><p class="sub">${d.bookings.length} ticket${d.bookings.length > 1 ? 's' : ''} confirmed.</p>${d.bookings.map(ticket).join('')}
      <div class="actions noprint"><button class="btn" onclick="window.print()">Print tickets</button><button class="btn primary" data-act="close">Done</button></div>`, true);
  } catch (x) {
    el.disabled = false;
    if (/taken/.test(x.message)) { const s = await api(`/api/trips/${BK.trip.id}/seats`); BK.booked = s.booked; BK.sel = []; renderBK(); }
    throw x;
  }
};

V['customer.tickets'] = async () => {
  const [rows, wait] = await Promise.all([api('/api/my/bookings'), api('/api/my/waitlist')]);
  main.innerHTML = `<h1>My tickets</h1>${findBox()}
    <div class="panel"><div class="row" style="justify-content:space-between;align-items:center;margin-bottom:.8rem"><h3>Bookings</h3>
    <button class="btn sm" data-act="undo">Undo last booking</button></div>${bookingsTable(rows, { cancel: true })}</div>
    ${wait.length ? `<div class="panel"><h3>On the waitlist</h3><div class="tablewrap"><table><thead><tr><th>Trip</th><th>Departs</th><th>Seats</th><th>Class</th><th></th></tr></thead><tbody>${wait.map(w => `<tr><td>${esc(w.source)} to ${esc(w.dest)}</td><td>${fdate(w.travel_date)}, ${esc(w.departure_time)}</td><td>${w.seats_needed}</td><td>${esc(w.seat_class)}</td><td><button class="btn sm danger" data-act="unwait" data-id="${w.id}">Leave waitlist</button></td></tr>`).join('')}</tbody></table></div></div>` : ''}`;
};
ACT.cancel = async el => {
  if (!confirm(`Cancel ticket ${el.dataset.pnr}? The refund depends on how close the departure is.`)) return;
  toast((await api(`/api/bookings/${el.dataset.id}/cancel`, 'POST')).message); go('tickets');
};
ACT.undo = async () => {
  if (!confirm('Undo your most recent booking? You will get a full refund.')) return;
  toast((await api('/api/undo', 'POST')).message); go('tickets');
};
ACT.unwait = async el => { toast((await api(`/api/waitlist/${el.dataset.id}/cancel`, 'POST')).message); go('tickets'); };

/* ======================= MANAGER + ADMIN: trips ======================= */
async function tripsView() {
  const [trips, buses, routes] = await Promise.all([api('/api/manage/trips'), api('/api/manage/buses'), api('/api/routes')]);
  const up = trips.filter(t => t.status === 'SCHEDULED' && !t.departed);
  const sum = (a, k) => a.reduce((s, x) => s + (+x[k] || 0), 0);
  const routeOpts = routes.flatMap(r => [[r.city_a, r.city_b, `${r.a_name} to ${r.b_name}`], [r.city_b, r.city_a, `${r.b_name} to ${r.a_name}`]])
    .sort((a, b) => a[2].localeCompare(b[2])).map(([s, d, l]) => `<option value="${s},${d}">${esc(l)}</option>`).join('');
  main.innerHTML = `<h1>${me.role === 'admin' ? 'All trips' : 'My trips'}</h1>
    <div class="stats"><div class="stat"><b>${up.length}</b><span>Upcoming trips</span></div>
    <div class="stat"><b>${sum(up, 'booked')}</b><span>Seats booked on upcoming trips</span></div>
    <div class="stat"><b>${sum(up, 'waiting')}</b><span>Seats on waitlists</span></div>
    <div class="stat hot"><b>${money(sum(trips, 'revenue'))}</b><span>Revenue collected</span></div></div>
    <form class="panel row" id="tripForm"><label>Bus<select name="bus">${buses.map(b => `<option value="${b.id}">${esc(b.name)} (${esc(b.reg_no)})</option>`).join('')}</select></label>
    <label>Route<select name="route">${routeOpts}</select></label>
    <label>Date<input type="date" name="date" min="${localDay()}" value="${localDay()}" required></label>
    <label>Departure<input type="time" name="time" value="08:00" required></label>
    <label>Repeat<select name="repeat"><option value="1">This date only</option><option value="7">Daily for 7 days</option><option value="14">Daily for 14 days</option><option value="30">Daily for 30 days</option><option value="60">Daily for 60 days</option></select></label><button class="btn primary">Add trip</button></form>
    <div class="panel"><div class="tablewrap">${trips.length ? `<table><thead><tr><th>Route</th><th>Departs</th><th>Bus</th><th>Occupancy</th><th>Waitlist</th><th class="num">Revenue</th><th>Status</th><th></th></tr></thead><tbody>${trips.map(t => {
      const pct = Math.round(t.booked / t.total_seats * 100);
      return `<tr><td><b>${esc(t.source)} to ${esc(t.dest)}</b></td><td>${fdate(t.travel_date)}, ${esc(t.departure_time)}</td><td>${esc(t.bus_name)}</td>
      <td>${t.booked}/${t.total_seats}<div class="bar"><i class="${pct > 85 ? 'hi' : ''}" style="width:${pct}%"></i></div></td><td>${t.waiting || '-'}</td>
      <td class="num">${money(t.revenue)}</td><td>${t.status === 'CANCELLED' ? '<span class="chip bad">Cancelled</span>' : t.departed ? '<span class="chip">Departed</span>' : '<span class="chip ok">Scheduled</span>'}</td>
      <td><button class="btn sm" data-act="detail" data-id="${t.id}">Details</button></td></tr>`;
    }).join('')}</tbody></table>` : '<div class="empty">No trips yet. Add the first one above.</div>'}</div></div>`;
  $('#tripForm').onsubmit = guard(async e => {
    e.preventDefault();
    const f = e.target, [s, d] = f.route.value.split(',');
    const r = await api('/api/manage/trips', 'POST', { bus_id: f.bus.value, source_id: s, dest_id: d, date: f.date.value, time: f.time.value, repeat_days: f.repeat.value });
    toast(r.message); go(current);
  });
}
ACT.detail = async el => {
  const d = await api(`/api/manage/trips/${el.dataset.id}/details`), t = d.trip;
  const live = t.status === 'SCHEDULED' && pdt(t.dep) > new Date();
  openModal(`<h2>${esc(t.source)} to ${esc(t.dest)}</h2><p class="sub">${fdate(t.travel_date)}, ${hm(t.dep)} &middot; ${esc(t.bus_name)} &middot; ${d.manifest.length}/${t.total_seats} seats booked</p>
    <h3>Passengers</h3>${d.manifest.length ? `<div class="tablewrap"><table><thead><tr><th>Seat</th><th>Passenger</th><th>PNR</th><th>Class</th><th class="num">Fare</th></tr></thead><tbody>${d.manifest.map(b => `<tr><td>${b.seat_no}</td><td>${esc(b.passenger_name)}, ${b.age}</td><td>${esc(b.pnr)}</td><td>${esc(b.seat_class)}</td><td class="num">${money(b.fare)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No bookings yet.</div>'}
    <h3 style="margin-top:1.2rem">Waitlist</h3>${d.waitlist.length ? `<div class="tablewrap"><table><thead><tr><th>Name</th><th>Seats</th><th>Class</th><th>Joined</th></tr></thead><tbody>${d.waitlist.map(w => `<tr><td>${esc(w.name)}</td><td>${w.seats_needed}</td><td>${esc(w.seat_class)}</td><td>${esc(w.created_at)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Nobody is waiting.</div>'}
    ${live ? `<div class="actions" style="margin-top:1.2rem">
      ${d.waitlist.length && d.free ? `<button class="btn" data-act="fill" data-id="${t.id}" data-s="order">Fill free seats in order of arrival</button><button class="btn" data-act="fill" data-id="${t.id}" data-s="revenue">Fill free seats for best revenue</button>` : ''}
      <button class="btn danger" data-act="cxTrip" data-id="${t.id}">Cancel this trip</button></div>` : ''}`);
};
ACT.fill = async el => { toast((await api(`/api/manage/trips/${el.dataset.id}/fill`, 'POST', { strategy: el.dataset.s })).message); closeModal(); go(current); };
ACT.cxTrip = async el => {
  if (!confirm('Cancel this trip? Every ticket will be refunded in full.')) return;
  toast((await api(`/api/manage/trips/${el.dataset.id}/cancel`, 'POST')).message); closeModal(); go(current);
};
V['manager.trips'] = tripsView;
V['admin.trips'] = tripsView;
V['manager.find'] = async () => { main.innerHTML = `<h1>Find a ticket</h1>${findBox()}<p class="muted">Search any ticket on your buses by its PNR.</p>`; };

/* ======================= ADMIN ======================= */
V['admin.overview'] = async () => {
  const s = await api('/api/admin/stats');
  main.innerHTML = `<h1>Overview</h1><div class="stats">
    <div class="stat hot"><b>${money(s.revenue)}</b><span>Net revenue</span></div>
    <div class="stat"><b>${s.confirmed}</b><span>Confirmed tickets</span></div>
    <div class="stat"><b>${s.cancelled}</b><span>Cancelled tickets</span></div>
    <div class="stat"><b>${s.upcoming}</b><span>Upcoming trips</span></div>
    <div class="stat"><b>${s.waiting}</b><span>Seats on waitlists</span></div>
    <div class="stat"><b>${s.buses}</b><span>Buses</span></div>
    <div class="stat"><b>${s.managers}</b><span>Bus managers</span></div>
    <div class="stat"><b>${s.customers}</b><span>Customers</span></div></div>
    <div class="panel"><h3>Top routes by revenue</h3>${s.by_route.length ? `<div class="tablewrap"><table><thead><tr><th>Route</th><th class="num">Tickets</th><th class="num">Revenue</th></tr></thead><tbody>${s.by_route.map(r => `<tr><td>${esc(r.source)} to ${esc(r.dest)}</td><td class="num">${r.tickets}</td><td class="num">${money(r.revenue)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No bookings yet.</div>'}</div>`;
};
V['admin.network'] = async () => {
  const [cities, routes] = await Promise.all([api('/api/cities'), api('/api/routes')]);
  const opt = cities.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
  main.innerHTML = `<h1>Cities & routes</h1>
    <div class="panel"><h3>Cities</h3><form class="row" id="cityForm"><label>New city<input name="name" required></label><button class="btn primary">Add city</button></form>
    <div class="actions" style="margin-top:1rem">${cities.map(c => `<span class="chip">${esc(c.name)} <a href="#" data-act="delCity" data-id="${c.id}" aria-label="Remove ${esc(c.name)}" style="color:var(--red);text-decoration:none">&times;</a></span>`).join('')}</div></div>
    <div class="panel"><h3>Routes</h3><form class="row" id="routeForm"><label>City A<select name="a">${opt}</select></label><label>City B<select name="b">${opt}</select></label>
    <label>Distance (km)<input name="km" type="number" min="1" required></label><button class="btn primary">Add route</button></form>
    <div class="tablewrap" style="margin-top:1rem"><table><thead><tr><th>Between</th><th class="num">Distance</th><th></th></tr></thead><tbody>${routes.map(r => `<tr><td>${esc(r.a_name)} and ${esc(r.b_name)}</td><td class="num">${r.distance_km} km</td><td><button class="btn sm danger" data-act="delRoute" data-id="${r.id}">Remove</button></td></tr>`).join('')}</tbody></table></div></div>`;
  $('#routeForm').b.selectedIndex = Math.min(1, cities.length - 1);
  $('#cityForm').onsubmit = guard(async e => { e.preventDefault(); toast((await api('/api/admin/cities', 'POST', { name: e.target.elements.name.value })).message); go('network'); });
  $('#routeForm').onsubmit = guard(async e => { e.preventDefault(); const f = e.target; toast((await api('/api/admin/routes', 'POST', { city_a: f.a.value, city_b: f.b.value, distance_km: f.km.value })).message); go('network'); });
};
const removal = (path, label) => async el => {
  if (!confirm(`Remove this ${label}?`)) return;
  toast((await api(`${path}/${el.dataset.id}`, 'DELETE')).message); go(current);
};
ACT.delCity = (el, e) => { e.preventDefault(); return removal('/api/admin/cities', 'city')(el); };
ACT.delRoute = removal('/api/admin/routes', 'route');
ACT.delBus = removal('/api/admin/buses', 'bus');
ACT.delUser = removal('/api/admin/users', 'account');

V['admin.buses'] = async () => {
  const [buses, users] = await Promise.all([api('/api/admin/buses'), api('/api/admin/users')]);
  const mgrs = users.filter(u => u.role === 'manager');
  const mopt = sel => `<option value="">Unassigned</option>` + mgrs.map(m => `<option value="${m.id}" ${m.id === sel ? 'selected' : ''}>${esc(m.name)}</option>`).join('');
  main.innerHTML = `<h1>Buses</h1><form class="panel row" id="busForm"><label>Registration<input name="reg" required></label><label>Bus name<input name="name" required></label>
    <label>Seats<input name="seats" type="number" min="8" max="60" step="4" value="40" required></label><label>Rate per km (₹)<input name="rate" type="number" step="0.1" min="0.1" value="2.2" required></label>
    <label>Manager<select name="mgr">${mopt()}</select></label><button class="btn primary">Add bus</button></form>
    <div class="panel"><div class="tablewrap"><table><thead><tr><th>Bus</th><th>Registration</th><th>Seats</th><th class="num">Rate / km</th><th>Manager</th><th></th></tr></thead><tbody>${buses.map(b => `<tr><td><b>${esc(b.name)}</b></td><td>${esc(b.reg_no)}</td><td>${b.total_seats}</td><td class="num">${money(b.rate_per_km)}</td>
    <td><select data-assign="${b.id}" style="margin:0">${mopt(b.manager_id)}</select></td><td><button class="btn sm danger" data-act="delBus" data-id="${b.id}">Remove</button></td></tr>`).join('')}</tbody></table></div></div>`;
  $('#busForm').onsubmit = guard(async e => { e.preventDefault(); const f = e.target; toast((await api('/api/admin/buses', 'POST', { reg_no: f.reg.value, name: f.elements.name.value, total_seats: f.seats.value, rate_per_km: f.rate.value, manager_id: f.mgr.value })).message); go('buses'); });
};
document.addEventListener('change', guard(async e => {
  if (e.target.dataset && e.target.dataset.assign) toast((await api(`/api/admin/buses/${e.target.dataset.assign}/manager`, 'POST', { manager_id: e.target.value })).message);
}));
V['admin.people'] = async () => {
  const users = await api('/api/admin/users');
  main.innerHTML = `<h1>People</h1><form class="panel row" id="userForm"><label>Full name<input name="name" required></label><label>Username<input name="username" required minlength="3"></label>
    <label>Password<input name="password" type="password" required minlength="6"></label><label>Role<select name="role"><option value="manager">Bus manager</option><option value="customer">Customer</option><option value="admin">Admin</option></select></label><button class="btn primary">Create account</button></form>
    <div class="panel"><div class="tablewrap"><table><thead><tr><th>Name</th><th>Username</th><th>Role</th><th></th></tr></thead><tbody>${users.map(u => `<tr><td><b>${esc(u.name)}</b></td><td>${esc(u.username)}</td><td><span class="chip ${u.role === 'admin' ? 'warn' : u.role === 'manager' ? 'ok' : ''}">${ROLES[u.role]}</span></td>
    <td>${u.id === me.id ? '<small>You</small>' : `<button class="btn sm danger" data-act="delUser" data-id="${u.id}">Remove</button>`}</td></tr>`).join('')}</tbody></table></div></div>`;
  $('#userForm').onsubmit = guard(async e => { e.preventDefault(); const f = e.target; toast((await api('/api/admin/users', 'POST', { name: f.elements.name.value, username: f.username.value, password: f.password.value, role: f.role.value })).message); go('people'); });
};
V['admin.bookings'] = async () => {
  const rows = await api('/api/admin/bookings');
  main.innerHTML = `<h1>Bookings</h1>${findBox()}<div class="panel"><h3>Latest 300 tickets</h3>${bookingsTable(rows, { who: true })}</div>`;
};

/* ---------- start */
(async () => {
  try { me = await api('/api/me'); showApp(); } catch (e) { showLogin(); }
})();