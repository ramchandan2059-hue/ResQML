// MediGuard — multi-page site controller (hash routing, no backend changes needed)

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const vis = (el, on) => el.classList.toggle('hidden', !on);
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// ---------------- State ----------------
let meds = [];                  // [{name, dose, frequency}]
let profile = { age: '', sex: 'Male', conditions: '', duration: '', frailty: '' };
let patientId = null;           // null → a fresh backend case is created on check
let lang = 'en';
let step = 1;
let lastSummary = null;
let lastGraph = null;
let busy = false;

const TITLES = {
  home: 'MediGuard — AI Medicine Safety Checker',
  check: 'Check medicines — MediGuard',
  samples: 'Sample cases — MediGuard'
};

document.addEventListener('DOMContentLoaded', () => {
  bindGlobal();
  bindChecker();
  setupPhotoScanner();
  setupMedicineMouseInteractions();
  window.addEventListener('hashchange', route);
  route();
  loadSystemStatus();
  renderMedList();
});

/* =================== Router =================== */
function route() {
  let page = (location.hash || '#/').replace(/^#\/?/, '').split('?')[0] || 'home';
  if (!TITLES[page]) page = 'home';
  document.body.dataset.page = page;
  const medBg = $('floatingMedBg');
  if (medBg) medBg.dataset.page = page;
  document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.dataset.page === page));
  document.querySelectorAll('#navLinks a').forEach(a => a.classList.toggle('active', a.dataset.route === page));
  $('navLinks').classList.remove('open');
  document.title = TITLES[page];
  window.scrollTo({ top: 0 });
  if (page === 'samples') loadSampleChips();
}
function go(page) { location.hash = '#/' + (page === 'home' ? '' : page); }

/* =================== Global UI =================== */
function bindGlobal() {
  $('burger').addEventListener('click', () => $('navLinks').classList.toggle('open'));

  // modals
  document.querySelectorAll('.modal-backdrop').forEach(m => m.addEventListener('click', (e) => { if (e.target === m) m.style.display = 'none'; }));
  const openSettings = (e) => { if (e) e.preventDefault(); $('settingsModal').style.display = 'flex'; };
  $('openSettingsBtn').addEventListener('click', openSettings);
  $('footSettings').addEventListener('click', openSettings);
  $('closeSettingsModal').addEventListener('click', () => { $('settingsModal').style.display = 'none'; });
  $('saveGroqKeyBtn').addEventListener('click', async () => {
    const key = $('groqApiKeyInput').value.trim();
    if (!key) return;
    try {
      const res = await fetch('/api/settings/groq-key', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ api_key: key }) });
      const data = await res.json();
      alert(data.message || 'Key saved!');
      $('settingsModal').style.display = 'none';
    } catch (e) { alert('Could not save the key.'); }
  });

  // sample cards
  document.querySelectorAll('[data-sample]').forEach(b => b.addEventListener('click', () => runSample(parseInt(b.dataset.sample))));
}

async function loadSystemStatus() {
  try {
    const res = await fetch('/api/system/status');
    const data = await res.json();
    if (data.status === 'online') {
      const n = Number(data.database.total_interactions_indexed);
      $('systemStatusBadge').textContent = `● ${n.toLocaleString()} interactions indexed`;
      $('statInteractions').textContent = n.toLocaleString() + '+';
    }
  } catch (e) { /* keep defaults */ }
}

async function loadSampleChips() {
  for (const n of [1, 2, 3]) {
    const box = document.querySelector(`[data-meds="${n}"]`);
    if (!box || box.dataset.loaded) continue;
    try {
      const res = await fetch(`/api/patient/${n}`);
      const data = await res.json();
      box.innerHTML = (data.medications || []).map(m => `<span>${esc(m.medicine_name)}</span>`).join('');
      box.dataset.loaded = '1';
    } catch (e) { /* leave empty */ }
  }
}

/* =================== Checker wizard =================== */
function bindChecker() {
  $('skipStep1').addEventListener('click', () => goStep(2));
  $('toStep2').addEventListener('click', () => { saveProfile(); goStep(2); });
  $('backStep1').addEventListener('click', () => goStep(1));
  $('checkBtn').addEventListener('click', runCheck);
  $('editMedsBtn').addEventListener('click', () => goStep(2));
  $('newCheckBtn').addEventListener('click', resetAll);
  $('pdfBtn').addEventListener('click', generatePdf);

  document.querySelectorAll('#stepper li').forEach(li => li.addEventListener('click', () => {
    const n = parseInt(li.dataset.step);
    if (li.classList.contains('done') && !busy) goStep(n);
  }));

  // medicine input + autocomplete
  const input = $('medSearchInput'), dd = $('autocompleteDropdown');
  let t = null;
  input.addEventListener('input', () => {
    clearTimeout(t);
    const q = input.value.trim();
    if (!q) { dd.style.display = 'none'; return; }
    t = setTimeout(async () => {
      try {
        const res = await fetch(`/api/medicines/search?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        renderAutocomplete(data.results || []);
      } catch (e) { /* ignore */ }
    }, 200);
  });
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); addFromInput(); } });
  $('medDoseInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); addFromInput(); } });
  document.addEventListener('click', (e) => { if (!input.contains(e.target) && !dd.contains(e.target)) dd.style.display = 'none'; });
  $('addMedBtn').addEventListener('click', addFromInput);

  // tabs
  document.querySelectorAll('#resultTabs .tab').forEach(tab => tab.addEventListener('click', () => {
    document.querySelectorAll('#resultTabs .tab').forEach(x => x.classList.toggle('active', x === tab));
    ['overview', 'interactions', 'map'].forEach(n => $('tab-' + n).classList.toggle('hidden', n !== tab.dataset.tab));
  }));

  // language
  document.querySelectorAll('.lang-btn').forEach(b => b.addEventListener('click', () => {
    document.querySelectorAll('.lang-btn').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    lang = b.dataset.lang;
    if (lastSummary && !busy) loadExplanation();
  }));
}

function goStep(n) {
  step = n;
  [1, 2, 3].forEach(i => $('step' + i).classList.toggle('hidden', i !== n));
  document.querySelectorAll('#stepper li').forEach(li => {
    const i = parseInt(li.dataset.step);
    li.classList.toggle('active', i === n);
    li.classList.toggle('done', i < n);
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function saveProfile() {
  profile = { age: $('patientAge').value, sex: $('patientSex').value, conditions: $('patientConditions').value.trim(), duration: $('patientDuration').value.trim(), frailty: $('patientFrailty').value.trim() };
  patientId = null;
}

function resetAll() {
  meds = []; patientId = null; lastSummary = null; lastGraph = null;
  profile = { age: '', sex: 'Male', conditions: '', duration: '', frailty: '' };
  ['patientAge', 'patientConditions', 'patientDuration', 'patientFrailty'].forEach(id => $(id).value = '');
  $('patientSex').value = 'Male';
  $('resultsBody').classList.add('hidden');
  renderMedList();
  goStep(1);
}

/* ---------- Medicines ---------- */
function renderAutocomplete(items) {
  const dd = $('autocompleteDropdown');
  dd.innerHTML = '';
  if (!items.length) { dd.style.display = 'none'; return; }
  items.forEach(m => {
    const d = document.createElement('div');
    d.className = 'ac-item';
    d.innerHTML = `${esc(m.name)}<span>${esc(m.category || '')}</span>`;
    d.addEventListener('click', () => { $('medSearchInput').value = m.name; dd.style.display = 'none'; $('medDoseInput').focus(); });
    dd.appendChild(d);
  });
  dd.style.display = 'block';
}

function addMed(name, dose = '', frequency = '') {
  name = (name || '').trim();
  if (!name) return false;
  if (meds.some(m => m.name.toLowerCase() === name.toLowerCase())) return false;
  meds.push({ name, dose, frequency: frequency || 'Once daily' });
  patientId = null;
  renderMedList();
  return true;
}
function addFromInput() {
  const names = $('medSearchInput').value.split(/[,;\n]+/);
  const dose = names.length === 1 ? $('medDoseInput').value.trim() : '';
  names.forEach(n => addMed(n, dose));
  $('medSearchInput').value = ''; $('medDoseInput').value = '';
  $('autocompleteDropdown').style.display = 'none';
  $('medSearchInput').focus();
}
window.removeMed = (i) => { meds.splice(i, 1); patientId = null; renderMedList(); };

function renderMedList() {
  const box = $('medList');
  box.innerHTML = meds.length
    ? meds.map((m, i) => `<div class="med-item"><div class="med-ico">💊</div><div class="med-info"><b>${esc(m.name)}</b><small>${esc(m.dose || 'Dose not given')}</small></div><button class="x" title="Remove" onclick="removeMed(${i})">✕</button></div>`).join('')
    : '<div class="med-empty">No medicines yet.<br>Type a name above, or scan a box with the camera.</div>';
  $('checkBtn').disabled = meds.length === 0 || busy;
  $('checkBtn').textContent = meds.length ? `✨ Check safety (${meds.length})` : '✨ Check safety';
}

/* ---------- Samples ---------- */
async function runSample(n) {
  if (busy) return;
  go('check');
  try {
    const res = await fetch(`/api/patient/${n}`);
    const data = await res.json();
    const p = data.patient;
    profile = { age: String(p.age), sex: p.biological_sex, conditions: p.conditions || '', duration: p.condition_duration || '', frailty: p.frailty_allergies || '' };
    $('patientAge').value = profile.age; $('patientSex').value = profile.sex; $('patientConditions').value = profile.conditions;
    $('patientDuration').value = profile.duration; $('patientFrailty').value = profile.frailty;
    meds = (data.medications || []).map(m => ({ name: m.medicine_name, dose: m.dose || '', frequency: m.frequency || 'Once daily' }));
    patientId = n;
    renderMedList();
    goStep(2);
    await runCheck();
  } catch (e) { alert('Could not load the sample case. Is the server running?'); }
}

/* =================== Analysis =================== */
async function ensurePatient() {
  if (patientId) return patientId;
  const res = await fetch('/api/patient', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      age: parseInt(profile.age) || 65, biological_sex: profile.sex || 'Male',
      conditions: profile.conditions || 'Not specified', condition_duration: profile.duration || '', frailty_allergies: profile.frailty || ''
    })
  });
  const data = await res.json();
  patientId = data.patient_id;
  for (const m of meds) {
    await fetch(`/api/patient/${patientId}/medications`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ medicine_name: m.name, dose: m.dose || '', frequency: m.frequency || 'Once daily', duration: '' })
    });
  }
  return patientId;
}

async function runCheck() {
  if (busy || !meds.length) return;
  busy = true; renderMedList();
  goStep(3);
  $('resultsBody').classList.add('hidden');
  $('resultsLoading').classList.remove('hidden');

  const msgs = ['Looking up interactions…', 'Comparing every pair of medicines…', 'Scoring the risk…'];
  let mi = 0; $('loadSub').textContent = msgs[0];
  const timer = setInterval(() => { mi = (mi + 1) % msgs.length; $('loadSub').textContent = msgs[mi]; }, 900);

  try {
    await ensurePatient();
    const res = await fetch(`/api/analyze/${patientId}`, { method: 'POST' });
    const data = await res.json();
    if (data.status !== 'success') throw new Error('analysis failed');
    lastSummary = data.risk_summary; lastGraph = data.network_graph;
    await sleep(700);
    clearInterval(timer);
    $('resultsLoading').classList.add('hidden');
    $('resultsBody').classList.remove('hidden');
    renderResults(lastSummary);
    document.querySelector('#resultTabs .tab[data-tab="overview"]').click();
    busy = false; renderMedList();
    loadExplanation();
  } catch (e) {
    clearInterval(timer);
    $('resultsLoading').classList.add('hidden');
    busy = false; renderMedList();
    alert('Something went wrong while checking. Please try again.');
    goStep(2);
  }
}

/* =================== Results =================== */
function classify(summary) {
  const t = { crit: [], mod: [], min: [], notes: [] };
  const seen = new Set();
  (summary.findings || []).forEach(f => {
    if (f.type === 'polypharmacy_count') { t.notes.push(`💊 ${summary.total_medicines} medicines taken at once`); return; }
    if (f.type === 'duplicate_class') { t.notes.push(`🔄 Two medicines of the same type: ${f.medicine_1} + ${f.medicine_2}`); return; }
    if (f.type === 'patient_factor') { t.notes.push(`👤 ${f.title}`); return; }
    const key = f.medicine_1 && f.medicine_2 ? [f.medicine_1, f.medicine_2].map(s => s.toLowerCase()).sort().join('_') : f.title;
    if (seen.has(key)) return; seen.add(key);
    const s = (f.severity || 'Moderate').toLowerCase();
    if (s === 'major' || s === 'high') t.crit.push(f);
    else if (s === 'moderate' || s === 'medium') t.mod.push(f);
    else t.min.push(f);
  });
  return t;
}

function plainHeadline(f) {
  const title = f.title || '';
  const has = (a, b) => title.includes(a) && title.includes(b);
  if (has('Warfarin', 'Aspirin')) return 'Together they can cause serious bleeding';
  if (has('Warfarin', 'Ibuprofen')) return 'High risk of stomach bleeding';
  if (has('Lisinopril', 'Losartan')) return 'Can raise potassium and strain the kidneys';
  if (has('Lisinopril', 'Ibuprofen')) return 'Can weaken BP medicine and harm the kidneys';
  if (has('Atorvastatin', 'Cobicistat')) return 'Can cause muscle damage';
  if (has('Simvastatin', 'Amlodipine')) return 'Statin level in the blood goes up';
  const first = (f.explanation || 'These medicines interact').split('.')[0];
  return first.length > 80 ? first.slice(0, 78) + '…' : first;
}

function findingHTML(f, cls, tag, icon) {
  const pair = f.medicine_1 && f.medicine_2 ? `${f.medicine_1} + ${f.medicine_2}` : f.title;
  return `
  <details class="finding ${cls}">
    <summary><span class="f-ico">${icon}</span>
      <span class="f-main"><div class="f-pair">${esc(pair)}</div><div class="f-sum">${esc(plainHeadline(f))}</div></span>
      <span class="f-tag">${tag}</span><span class="f-caret">›</span></summary>
    <div class="f-body">
      <h5>Why this matters</h5>${esc(f.explanation || 'These medicines are known to interact.')}
      <h5>What to do</h5>Don't stop anything on your own. Show this to your doctor or pharmacist — they may change a medicine, adjust the dose, or arrange a check-up.
      <div class="f-ref">Source: ${esc(f.reference || 'DDInter database / British National Formulary')}</div>
    </div>
  </details>`;
}

const VERDICT = {
  HIGH:   { icon: '🔴', title: 'Please talk to a doctor or pharmacist soon', sub: 'I found serious combinations. Do not stop any medicine yourself — get the list reviewed.', pos: 88 },
  MEDIUM: { icon: '🟡', title: 'Be careful — a few things to check', sub: 'Some combinations need watching. Mention them at your next visit.', pos: 52 },
  LOW:    { icon: '🟢', title: 'Looks fairly safe', sub: "I didn't find serious problems. Still, keep your doctor informed about everything you take.", pos: 14 }
};

function renderResults(summary) {
  const level = summary.risk_level || 'LOW';
  const v = VERDICT[level] || VERDICT.LOW;
  const t = classify(summary);

  $('verdict').className = `verdict ${level}`;
  $('verdict').innerHTML = `
    <div class="big">${v.icon}</div>
    <div style="flex:1"><h2>${v.title}</h2><p>${v.sub}</p><div class="meter"><i style="left:0%"></i></div></div>`;
  requestAnimationFrame(() => requestAnimationFrame(() => { const i = $('verdict').querySelector('.meter i'); if (i) i.style.left = v.pos + '%'; }));

  $('resultChips').innerHTML = `
    <span class="pill">${summary.total_medicines} medicines</span>
    ${t.crit.length ? `<span class="pill r">${t.crit.length} serious</span>` : ''}
    ${t.mod.length ? `<span class="pill a">${t.mod.length} to watch</span>` : ''}
    ${t.min.length ? `<span class="pill b">${t.min.length} minor</span>` : ''}`;

  // Interactions tab
  let html = '';
  if (t.crit.length + t.mod.length + t.min.length === 0) {
    html = '<div class="ok-box">✓ No harmful combinations found in the database for these medicines.</div>';
  } else {
    if (t.crit.length) html += '<div class="tier-title t1">🚨 Serious — talk to a doctor soon</div>' + t.crit.map(f => findingHTML(f, 'crit', 'Serious', '🚨')).join('');
    if (t.mod.length) html += '<div class="tier-title t2">⚠️ Be careful</div>' + t.mod.map(f => findingHTML(f, 'mod', 'Be careful', '⚠️')).join('');
    if (t.min.length) html += '<div class="tier-title t3">ℹ️ Minor</div>' + t.min.map(f => findingHTML(f, 'min', 'Minor', 'ℹ️')).join('');
  }
  $('findingsList').innerHTML = html;

  // Notes (overview tab)
  $('notesPanel').innerHTML = t.notes.length
    ? '<div class="panel"><h2 style="font-size:1.05rem;margin-bottom:10px">Other things I noticed</h2>' + t.notes.map(n => `<span class="note-chip">${esc(n)}</span>`).join('') + '</div>'
    : '';

  drawGraph(lastGraph);
}

/* ---------- AI explanation ---------- */
async function loadExplanation() {
  const box = $('aiExplanationContent');
  box.innerHTML = '<div class="skeleton"></div>';
  try {
    const res = await fetch('/api/explain', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_id: patientId, language: lang })
    });
    const data = await res.json();
    const exp = data.explanation;
    const raw = exp.text || '';
    let a = '', b = '', c = '';
    raw.split(/###\s+/).forEach(s => {
      const clean = s.trim(); if (!clean) return;
      const lines = clean.split('\n').map(l => l.trim()).filter(Boolean);
      const h = lines[0].toLowerCase(), body = lines.slice(1).join(' ');
      if (h.includes('summary') || h.includes('what this means')) { const s2 = body.split(/\.\s+/); a = s2.slice(0, 2).join('. ').replace(/\.+$/, '') + '.'; }
      else if (h.includes('key medicines') || h.includes('flags') || h.includes('warnings')) {
        const bl = lines.filter(l => /^[*-]/.test(l)); b = bl.length ? bl.slice(0, 2).map(x => x.replace(/^[-*]\s*/, '').replace(/\*\*/g, '')).join(' • ') : body.slice(0, 160) + '…';
      } else if (h.includes('questions') || h.includes('pharmacist')) {
        const bl = lines.filter(l => /^([*-]|\d+\.)/.test(l)); c = bl.length ? bl.slice(0, 2).map(x => x.replace(/^([-*]|\d+\.)\s*/, '').replace(/\*\*/g, '')).join(' • ') : body.slice(0, 160) + '…';
      }
    });
    if (!a) a = 'This combination needs a review by a doctor or pharmacist.';
    if (!b) b = 'Unusual bruising or bleeding, stomach pain, dizziness, swelling.';
    if (!c) c = 'Can any of these medicines be changed or safely monitored?';

    const full = esc(raw).replace(/^### (.*$)/gim, '<h4>$1</h4>').replace(/^[*-] (.*$)/gim, '<li>$1</li>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n\n/g, '<br>');
    box.innerHTML = `
      <div class="ai-cards">
        <div class="ai-card c1"><h4>⚠️ Main concern</h4><p>${esc(a)}</p></div>
        <div class="ai-card c2"><h4>🩺 Warning signs to watch</h4><p>${esc(b)}</p></div>
        <div class="ai-card c3"><h4>💬 Ask your doctor</h4><p>${esc(c)}</p></div>
      </div>
      <details class="more"><summary>📖 Read the full explanation</summary><div class="more-body">${full}</div></details>
      <div class="src">${exp.source === 'groq_llama_3.3_70b' ? 'Written by AI (Groq LLaMA-3.3-70B)' : 'Built-in clinical rules'} · interactions checked against the DDInter database</div>`;
  } catch (e) {
    box.innerHTML = '<p class="muted">I couldn’t write the plain-language summary this time, but the interaction results are still valid.</p>';
  }
}

/* ---------- Map ---------- */
function drawGraph(g) {
  const svg = $('graphSvg');
  svg.innerHTML = '';
  if (!g || !g.nodes || !g.nodes.length) return;
  const NS = 'http://www.w3.org/2000/svg', W = 560, H = 340, cx = W / 2, cy = H / 2, R = Math.min(cx, cy) - 55;
  const mk = (tag, at = {}) => { const e = document.createElementNS(NS, tag); Object.entries(at).forEach(([k, v]) => e.setAttribute(k, v)); return e; };
  const col = (s) => s === 'Major' ? '#e5484d' : (s === 'Moderate' ? '#f5a524' : '#3b82f6');
  const pos = {}, n = g.nodes.length;
  g.nodes.forEach((nd, i) => { const a = n === 1 ? 0 : (i / n) * 2 * Math.PI - Math.PI / 2; pos[nd.id] = { x: n === 1 ? cx : cx + R * Math.cos(a), y: n === 1 ? cy : cy + R * Math.sin(a), a }; });
  (g.edges || []).forEach(e => {
    const s = pos[e.source], t = pos[e.target]; if (!s || !t) return;
    svg.appendChild(mk('line', { x1: s.x, y1: s.y, x2: t.x, y2: t.y, stroke: col(e.severity), 'stroke-width': e.severity === 'Major' ? 4 : 2.4, 'stroke-linecap': 'round', 'stroke-dasharray': e.severity === 'Moderate' ? '6 4' : 'none', opacity: 0.85 }));
  });
  Object.entries(pos).forEach(([id, p]) => {
    svg.appendChild(mk('circle', { cx: p.x, cy: p.y, r: 22, fill: '#eef0ff', stroke: '#4f46e5', 'stroke-width': 2 }));
    const ic = mk('text', { x: p.x, y: p.y + 6, 'text-anchor': 'middle', 'font-size': 16 }); ic.textContent = '💊'; svg.appendChild(ic);
    const lb = mk('text', { x: p.x, y: p.y + (Math.sin(p.a) > 0.2 ? 42 : -32), 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 700, fill: '#334155' });
    lb.textContent = id.length > 14 ? id.slice(0, 13) + '…' : id; svg.appendChild(lb);
  });
}

/* ---------- PDF ---------- */
async function generatePdf() {
  if (!patientId) return;
  const btn = $('pdfBtn'), old = btn.textContent;
  btn.textContent = '⏳ Preparing…'; btn.disabled = true;
  try {
    const res = await fetch(`/api/generate-report/${patientId}`, { 
      method: 'POST', 
      headers: { 'Content-Type': 'application/json' }, 
      body: JSON.stringify({ patient_id: patientId, language: lang }) 
    });
    if (!res.ok) {
      let errMsg = 'Failed to generate report';
      try {
        const errJson = await res.json();
        errMsg = errJson.detail || errJson.message || errMsg;
      } catch (_) {
        errMsg = await res.text();
      }
      throw new Error(errMsg);
    }
    const data = await res.json();
    if (data.download_url) {
      window.open(data.download_url, '_blank');
    }
  } catch (e) { 
    alert('Could not create the report: ' + e.message); 
  } finally {
    btn.textContent = old; 
    btn.disabled = false;
  }
}

/* =================== Photo scanner =================== */
function setupPhotoScanner() {
  let photos = [], stream = null;
  const modal = $('photoModal'), video = $('webcamVideo'), canvas = $('webcamCanvas');
  const snap = $('snapPhotoBtn'), stop = $('stopCameraBtn'), scan = $('scanPhotoBtn'), prev = $('photoPreviewContainer'), file = $('photoFileInput');

  $('openPhotoUploadBtn').addEventListener('click', () => { modal.style.display = 'flex'; });
  const stopCam = () => { if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; } video.srcObject = null; snap.disabled = true; stop.disabled = true; };
  $('closePhotoModal').addEventListener('click', () => { stopCam(); modal.style.display = 'none'; });

  $('tabUploadMode').addEventListener('click', () => { stopCam(); vis($('uploadSection'), true); vis($('cameraSection'), false); $('tabUploadMode').classList.add('active'); $('tabCameraMode').classList.remove('active'); });
  $('tabCameraMode').addEventListener('click', async () => { vis($('uploadSection'), false); vis($('cameraSection'), true); $('tabCameraMode').classList.add('active'); $('tabUploadMode').classList.remove('active'); await startCam(); });

  async function startCam() {
    try { stopCam(); stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } } }); }
    catch (e) { try { stream = await navigator.mediaDevices.getUserMedia({ video: true }); } catch (e2) { alert('Camera not available: ' + e2.message); return; } }
    video.srcObject = stream; snap.disabled = false; stop.disabled = false;
  }
  $('startCameraBtn').addEventListener('click', startCam);
  stop.addEventListener('click', stopCam);

  function renderThumbs() {
    if (!photos.length) { vis(prev, false); vis(scan, false); return; }
    vis(prev, true);
    prev.innerHTML = `<div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:center">${photos.map((p, i) => `<div style="position:relative;width:84px;height:84px;border-radius:12px;overflow:hidden;border:2px solid #4f46e5"><img src="${p.url}" style="width:100%;height:100%;object-fit:cover" alt=""><button type="button" onclick="removePhoto(${i})" style="position:absolute;top:3px;right:3px;border:none;border-radius:50%;width:20px;height:20px;background:rgba(229,72,77,.92);color:#fff;font-size:11px;cursor:pointer">✕</button></div>`).join('')}</div>`;
    vis(scan, true);
    scan.textContent = `⚡ Read medicines from ${photos.length} photo${photos.length > 1 ? 's' : ''}`;
  }
  window.removePhoto = (i) => { photos.splice(i, 1); renderThumbs(); };

  snap.addEventListener('click', () => {
    if (!video.videoWidth) return;
    canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    canvas.toBlob(b => { photos.push({ blob: b, name: `snap_${photos.length + 1}.jpg`, url: URL.createObjectURL(b) }); renderThumbs(); }, 'image/jpeg', 0.92);
  });
  file.addEventListener('change', (e) => { Array.from(e.target.files).forEach(f => photos.push({ blob: f, name: f.name, url: URL.createObjectURL(f) })); renderThumbs(); });

  scan.addEventListener('click', async () => {
    const fd = new FormData();
    photos.forEach(p => fd.append('files', p.blob, p.name));
    scan.textContent = '⏳ Reading…'; scan.disabled = true;
    try {
      const res = await fetch('/api/upload-photo', { method: 'POST', body: fd });
      const data = await res.json();
      renderCandidates(data.candidates || []);
    } catch (e) { alert('Could not read the photo: ' + e.message); }
    scan.disabled = false; renderThumbs();
  });

  function renderCandidates(list) {
    const box = $('visionCandidatesList'), ok = $('confirmAddDetectedBtn');
    vis($('visionResultsContainer'), true);
    if (!list.length) { box.innerHTML = '<p class="muted">I couldn’t clearly read any medicine. Try a closer photo in good light.</p>'; vis(ok, false); return; }
    box.innerHTML = list.map(c => `
      <div class="cand">
        <div class="cn">💊 ${esc(c.name)}</div>
        <small>${esc(c.purpose || c.category || '')}</small>
        <div class="row">
          <input class="cand-name" value="${esc(c.name || '')}" placeholder="Medicine name">
          <input class="cand-dose" value="${esc(c.dose || '')}" placeholder="Dose">
          <button type="button" class="x" onclick="this.closest('.cand').remove()">✕</button>
        </div>
      </div>`).join('');
    vis(ok, true);
  }

  $('confirmAddDetectedBtn').addEventListener('click', () => {
    document.querySelectorAll('.cand').forEach(r => addMed(r.querySelector('.cand-name').value, r.querySelector('.cand-dose').value.trim()));
    stopCam(); modal.style.display = 'none';
    photos = []; renderThumbs();
    vis($('visionResultsContainer'), false); $('visionCandidatesList').innerHTML = '';
  });
}

/* =================== Medicine Mouse & Touch Interactivity =================== */
function setupMedicineMouseInteractions() {
  const bg = $('floatingMedBg');
  if (!bg) return;

  const items = Array.from(bg.querySelectorAll('.floating-med-item'));
  if (!items.length) return;

  // 1. Ambient gentle glow following the cursor
  const glow = document.createElement('div');
  glow.className = 'cursor-ambient-glow';
  glow.style.opacity = '0';
  document.body.appendChild(glow);

  let mouseX = -1000, mouseY = -1000;
  let targetGlowX = -1000, targetGlowY = -1000;
  let currentGlowX = -1000, currentGlowY = -1000;
  let isMoving = false;
  let idleTimeout = null;

  // 2. Track pointer (mouse move or mobile touch)
  window.addEventListener('pointermove', (e) => {
    mouseX = e.clientX;
    mouseY = e.clientY;
    targetGlowX = mouseX;
    targetGlowY = mouseY;
    glow.style.opacity = '1';
    isMoving = true;

    clearTimeout(idleTimeout);
    idleTimeout = setTimeout(() => {
      isMoving = false;
      glow.style.opacity = '0';
    }, 1800);
  }, { passive: true });

  // 3. Touch/Click creates an expanding glass ripple
  window.addEventListener('pointerdown', (e) => {
    createGlassRipple(e.clientX, e.clientY);
  });

  // Tap bounce on medicine items
  items.forEach(item => {
    item.addEventListener('click', (e) => {
      createGlassRipple(e.clientX, e.clientY);
      item.classList.remove('med-touched');
      void item.offsetWidth; // trigger reflow
      item.classList.add('med-touched');
      setTimeout(() => item.classList.remove('med-touched'), 550);
    });
  });

  function createGlassRipple(x, y) {
    if (x === undefined || y === undefined) return;
    const ripple = document.createElement('div');
    ripple.className = 'glass-ripple';
    ripple.style.left = `${x}px`;
    ripple.style.top = `${y}px`;
    document.body.appendChild(ripple);
    setTimeout(() => { if (ripple.parentNode) ripple.remove(); }, 850);
  }

  // 4. Smooth 3D magnetic reaction physics loop (RAF)
  function updatePhysics() {
    // Smooth glow interpolation
    currentGlowX += (targetGlowX - currentGlowX) * 0.12;
    currentGlowY += (targetGlowY - currentGlowY) * 0.12;
    glow.style.left = `${currentGlowX}px`;
    glow.style.top = `${currentGlowY}px`;

    // Magnetic nudge & 3D tilt for items near the cursor
    const radius = 140;
    items.forEach(item => {
      if (item.classList.contains('med-touched')) return;

      const rect = item.getBoundingClientRect();
      const itemCenterX = rect.left + rect.width / 2;
      const itemCenterY = rect.top + rect.height / 2;

      const dx = itemCenterX - mouseX;
      const dy = itemCenterY - mouseY;
      const dist = Math.hypot(dx, dy);

      if (dist < radius && isMoving) {
        const force = (1 - dist / radius);
        const moveX = (dx / dist) * force * 24;
        const moveY = (dy / dist) * force * 24;
        const tiltX = -(dy / radius) * force * 12;
        const tiltY = (dx / radius) * force * 12;

        item.style.transform = `translate3d(${moveX}px, ${moveY}px, 0) rotate(${tiltY}deg) scale(1.06)`;
      } else if (!item.matches(':hover')) {
        if (item.style.transform) {
          item.style.transform = '';
        }
      }
    });

    requestAnimationFrame(updatePhysics);
  }

  requestAnimationFrame(updatePhysics);
}
