/* 对戏剧场 DUO · 沉浸台本前端
   每轮：台词 + 内心OS + 招式tactic + 关系增量；服务端权威关系值；种进世界树；任意句 fork 重演。
   整页渲染成"剧本"：场景标题 → 角色名 → (括号提示=招式) → 台词 → 心声/动作行。
   分支单独做成弹出"故事地图"节点树。 */
const $ = (s) => document.querySelector(s);
const esc = (s) => { const d = document.createElement('div'); d.textContent = String(s == null ? '' : s); return d.innerHTML; };
const J = (e) => { try { return JSON.parse(e.data); } catch (_) { return {}; } };

let SID = null, RUNNING = false, ROUND = 0, MAX = 14, activeES = null, TREE = null, SELECTED = null;
let names = { A: 'A', B: 'B' }, curRel = 50;

function setStatus(t) { $('#d-status').textContent = t; }
function enablePlay(on) { ['#d-pause', '#d-inject', '#d-injectbtn', '#d-mapbtn'].forEach((s) => $(s).disabled = !on); }
function scrollScript() { const c = $('#d-script'); c.scrollTop = c.scrollHeight; }

/* —— 浮层开关 —— */
function openSetup() { if (RUNNING) togglePause(); $('#setup-modal').classList.add('show'); }
function closeSetup() { $('#setup-modal').classList.remove('show'); }
function openMap() { if (RUNNING) { RUNNING = false; $('#d-pause').textContent = '▶'; setStatus('已暂停 · 看地图'); } SELECTED = null; $('#duo-fork').hidden = true; renderTree(); $('#map-modal').classList.add('show'); }
function closeMap() { $('#map-modal').classList.remove('show'); $('#duo-fork').hidden = true; SELECTED = null; }

/* —— 关系仪表 + 情绪冷暖光 —— */
function relColor(r) {
  const t = Math.max(0, Math.min(1, r / 100));
  if (t < 0.5) return `rgb(255,${Math.round(106 + 37 * t * 2)},${Math.round(122 + 31 * t * 2)})`;
  const u = (t - 0.5) * 2;
  return `rgb(${Math.round(143 - 48 * u)},${Math.round(153 + 74 * u)},${Math.round(153 + u)})`;
}
function setRel(r, delta) {
  curRel = r;
  $('#d-relmark').style.left = r + '%';
  const val = $('#d-relval'); val.textContent = r; val.style.left = r + '%';
  $('#d-reltop').textContent = r;
  const amb = $('#stage-ambient'); if (amb) amb.style.setProperty('--warm', (r / 100).toFixed(3));
  const tr = $('#d-reltrack');
  if (delta != null && delta <= -8) { tr.classList.remove('crack'); void tr.offsetWidth; tr.classList.add('crack'); }
  if (delta != null && delta >= 8) { tr.classList.remove('warmflash'); void tr.offsetWidth; tr.classList.add('warmflash'); }
}

/* —— 开戏 —— */
function start() {
  if (activeES) { try { activeES.close(); } catch (_) {} activeES = null; }
  const q = new URLSearchParams({
    nameA: $('#d-nameA').value, personaA: $('#d-personaA').value, objectiveA: $('#d-objA').value, secretA: $('#d-secA').value, modelA: $('#d-modelA').value,
    nameB: $('#d-nameB').value, personaB: $('#d-personaB').value, objectiveB: $('#d-objB').value, secretB: $('#d-secB').value, modelB: $('#d-modelB').value,
    scene: $('#d-scene').value,
  });
  names = { A: $('#d-nameA').value.trim() || '角色A', B: $('#d-nameB').value.trim() || '角色B' };
  $('#d-rnA').textContent = names.A; $('#d-rnB').textContent = names.B;
  $('#d-injtgt').options[1].textContent = '私语→' + names.A;
  $('#d-injtgt').options[2].textContent = '私语→' + names.B;
  $('#d-forktgt').options[0].textContent = names.A;
  $('#d-forktgt').options[1].textContent = names.B;
  MAX = Math.max(2, Math.min(40, parseInt($('#d-max').value) || 14));
  $('#d-script').innerHTML = ''; ROUND = 0; $('#d-round').textContent = '0';
  const scene = $('#d-scene').value.trim();
  $('#d-slug').textContent = 'INT. ' + (scene.slice(0, 30) || '自由对戏');
  $('#duo-fork').hidden = true; SELECTED = null;
  closeSetup(); closeMap();
  setStatus('开场中…');
  const es = new EventSource('/api/duo/start?' + q.toString()); activeES = es;
  es.addEventListener('started', (e) => { SID = J(e).sid; setRel(J(e).rel || 50, null); });
  es.addEventListener('done', async () => {
    es.close(); activeES = null; enablePlay(true); $('#d-pause').textContent = '⏸';
    await refreshTree();
    RUNNING = true; runLoop();
  });
  es.onerror = () => { if (es.readyState === EventSource.CLOSED) return; try { es.close(); } catch (_) {} activeES = null; };
}

async function runLoop() {
  while (RUNNING && ROUND < MAX) {
    setStatus('对戏中…');
    const ok = await stepOnce();
    if (!ok) { RUNNING = false; setStatus('模型限流/出错，已暂停'); $('#d-pause').textContent = '▶'; return; }
    ROUND++; $('#d-round').textContent = ROUND;
    await refreshTree();
  }
  if (ROUND >= MAX) { RUNNING = false; setStatus('到达幕上限'); $('#d-pause').textContent = '▶'; spCurtain(); }
  else if (!RUNNING) setStatus('已暂停');
}

/* —— 一轮（实时流式）—— */
function stepOnce() {
  return new Promise((resolve) => {
    const es = new EventSource('/api/duo/step?sid=' + SID); activeES = es;
    let turnEl = null, ok = true;
    es.addEventListener('speaker', (e) => { const d = J(e); $('#duo-stage').dataset.spk = d.who; turnEl = liveSp(d.who, d.name); });
    es.addEventListener('turn', (e) => {
      const d = J(e);
      fillSp(turnEl, d);
      spBeat(d.rel_delta);
      setRel(d.rel, d.rel_delta);
      if (d.narr) spAction(d.narr, 'all');
      scrollScript();
    });
    es.addEventListener('error', (e) => {
      ok = false;
      if (turnEl) { turnEl.remove(); turnEl = null; }           // 撤掉半成品那一拍，别把错误当台词
      const sys = document.createElement('div'); sys.className = 'sp-sys';   // 破折号交给 CSS，台本旁注口吻、不漏后端英文
      sys.textContent = '此处一拍失语 · 模型一时没接上（超时或限流），点 ▶ 续戏';
      $('#d-script').appendChild(sys); scrollScript();
    });
    es.addEventListener('done', () => { es.close(); activeES = null; resolve(ok); });
    es.onerror = () => { if (es.readyState === EventSource.CLOSED) return; try { es.close(); } catch (_) {} activeES = null; resolve(false); };
  });
}

/* —— 剧本渲染：一句台词 = 一拍 —— */
function liveSp(who, name) {
  const t = document.createElement('div'); t.className = 'sp live ' + who;
  t.innerHTML = `<div class="sp-name">${esc(name)}</div>` +
    `<div class="sp-paren" hidden></div>` +
    `<div class="sp-line">（构思中<span class="caretdot"></span>）</div>`;
  $('#d-script').appendChild(t); scrollScript(); return t;
}
function fillSp(t, d) {
  if (!t) return;
  t.classList.remove('live');
  const p = t.querySelector('.sp-paren');
  if (d.tactic) { p.textContent = d.tactic; p.hidden = false; } else { p.remove(); }
  t.querySelector('.sp-line').innerHTML = esc(d.text);
  if (d.os) { const os = document.createElement('div'); os.className = 'sp-os'; os.textContent = d.os; t.appendChild(os); }
}
function spBeat(d) {
  const el = document.createElement('div');
  el.className = 'sp-beat ' + (d > 0 ? 'up' : d < 0 ? 'down' : 'zero');
  el.textContent = d > 0 ? '关系 +' + d : d < 0 ? '关系 ' + d : '关系 ±0';
  $('#d-script').appendChild(el);
}
function spAction(text, tgt) {
  const d = document.createElement('div'); d.className = 'sp-action' + (tgt && tgt !== 'all' ? ' aside' : '');
  d.textContent = (tgt && tgt !== 'all' ? '私语→' + (names[tgt] || tgt) + '：' : '') + text;
  $('#d-script').appendChild(d); scrollScript();
}
function spCurtain() {
  if ($('#d-script .sp-curtain')) return;
  const d = document.createElement('div'); d.className = 'sp-curtain'; d.textContent = '幕 · 落';
  $('#d-script').appendChild(d); scrollScript();
}

/* —— 导演 插一句 —— */
async function inject() {
  const t = $('#d-inject').value.trim(); if (!t || !SID) return;
  const tgt = $('#d-injtgt').value;
  $('#d-inject').value = '';
  try { await fetch(`/api/duo/inject?sid=${SID}&target=${tgt}&text=${encodeURIComponent(t)}`); } catch (_) {}
  spAction(t, tgt);
}

function togglePause() {
  if (!SID) return;
  if (RUNNING) { RUNNING = false; $('#d-pause').textContent = '▶'; setStatus('已暂停'); }
  else { if (ROUND >= MAX) MAX += 14; RUNNING = true; $('#d-pause').textContent = '⏸'; runLoop(); }
}
function reset() {
  RUNNING = false; if (activeES) { try { activeES.close(); } catch (_) {} activeES = null; }
  SID = null; ROUND = 0; TREE = null; SELECTED = null; $('#d-round').textContent = '0'; $('#d-reltop').textContent = '—';
  $('#d-script').innerHTML = '<div class="script-empty"><div class="se-curtain">· 幕 未 启 ·</div><p>填两个角色与场景，开戏。</p><button id="d-open-setup" class="duo-btn primary">▶ 摆 角 色 · 开 戏</button><div class="se-foot">灯 · 将 · 亮</div></div>';
  $('#d-open-setup').addEventListener('click', openSetup);
  $('#d-slug').textContent = 'INT. 待 开 场';
  $('#duo-fork').hidden = true; enablePlay(false); $('#d-pause').textContent = '⏸'; setStatus('待开场');
  $('#duo-tree').innerHTML = '<div class="duo-empty2">开戏后，每句台词在这里长成一棵可分叉的树。</div>';
}

/* ════ 故事地图 = 真·节点树（蓝图）════ */
async function refreshTree() {
  try { TREE = await (await fetch('/api/duo/timeline?sid=' + SID)).json(); } catch (_) { return; }
  if ($('#map-modal').classList.contains('show')) renderTree();
}
function renderTree() {
  const host = $('#duo-tree');
  if (!TREE) { host.innerHTML = '<div class="duo-empty2">开戏后，每句台词在这里长成一棵可分叉的树。</div>'; return; }
  const L = TreeLayout.layoutTree(TREE, { row: 78, lane: 176, x0: 66, y0: 48 });
  // 没选节点时，默认高亮"当前所在那条线"（最新节点回溯到根）→ you-are-here
  let hi = SELECTED;
  if (hi == null) { let mx = -1; for (const n of L.nodes) if (n.id > mx) { mx = n.id; } hi = mx >= 0 ? mx : null; }
  const path = hi != null ? new Set(TreeLayout.pathToRoot(L.byId, hi).map((n) => n.id)) : new Set();
  const W = Math.max(L.width + 240, 460), H = Math.max(L.height + 80, 240);
  let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">`;
  for (const e of L.edges) {                                   // 枝条（贝塞尔）：当前线金亮，旁支灰
    const a = e.from, b = e.to, my = (a.y + b.y) / 2, on = path.has(a.id) && path.has(b.id);
    s += `<path d="M${a.x},${a.y} C${a.x},${my} ${b.x},${my} ${b.x},${b.y}" fill="none" stroke="${on ? '#f2b24a' : '#27323f'}" stroke-width="${on ? 2.4 : 1.6}" stroke-linecap="round" opacity="${on ? 1 : .6}"/>`;
  }
  for (const n of L.nodes) {                                   // 节点：颜色=关系，标签=谁说·台词预览·关系值
    const st = n.state || {}, who = st.who, rel = st.rel, root = !who;
    const sel = n.id === SELECTED, on = path.has(n.id), r = sel ? 10 : 7;
    const col = root ? '#6a7686' : relColor(rel);
    const name = who ? (names[who] || who) : '幕起';
    const tcol = who === 'A' ? '#5fe8e2' : who === 'B' ? '#f4b85a' : '#8696ad';
    const preview = root ? '开场' : String(n.final || '').replace(/（[^）]*）/g, '').replace(/\s+/g, '').slice(0, 13);
    s += `<g data-cp="${n.id}" style="cursor:pointer">`;
    if (sel) s += `<circle cx="${n.x}" cy="${n.y}" r="${r + 5}" fill="none" stroke="#f2b24a" stroke-width="1.6"/>`;
    s += `<circle cx="${n.x}" cy="${n.y}" r="${r}" fill="${col}" stroke="rgba(3,5,10,.75)" stroke-width="1.4"/>`;
    s += `<text x="${n.x + r + 10}" y="${n.y - 2}" font-size="12.5" font-family="'Noto Serif SC',serif" font-weight="600" fill="${on ? tcol : 'rgba(190,205,225,.72)'}">${esc(name)}${root ? '' : ''}</text>`;
    s += `<text x="${n.x + r + 10}" y="${n.y + 13}" font-size="10.5" font-family="'JetBrains Mono',monospace" fill="${on ? '#9fb2cd' : '#5f7088'}">${esc(preview)}${root ? '' : '  · ' + rel}</text>`;
    s += `</g>`;
  }
  s += `</svg>`;
  host.innerHTML = s;
  host.querySelectorAll('[data-cp]').forEach((el) => { el.onclick = () => selectNode(+el.dataset.cp); });
}

function selectNode(cpId) {
  SELECTED = cpId; renderTree();
  $('#d-forkcp').textContent = 'cp' + cpId;
  $('#duo-fork').hidden = false;
}
function cancelFork() { $('#duo-fork').hidden = true; SELECTED = null; renderTree(); }

async function doFork() {
  if (SELECTED == null || !SID) return;
  const target = $('#d-forktgt').value, secret = $('#d-forksec').value.trim();
  let r;
  try { r = await (await fetch(`/api/duo/fork?sid=${SID}&cp_id=${SELECTED}&target=${target}&secret=${encodeURIComponent(secret)}`)).json(); } catch (_) { return; }
  if (!r || !r.ok) return;
  await refreshTree();
  closeMap();                                                 // 关地图，回剧本看新枝
  renderPathScript(SELECTED);
  const mk = document.createElement('div'); mk.className = 'sp-fork';
  mk.textContent = `⏪ 从这里分叉重演` + (secret ? ` · 给 ${names[target] || target} 塞了秘密：「${secret}」` : '');
  $('#d-script').appendChild(mk);
  setRel(r.rel, null);
  $('#d-forksec').value = ''; SELECTED = null;
  ROUND = document.querySelectorAll('#d-script .sp').length;
  MAX = ROUND + 6; $('#d-round').textContent = ROUND;
  RUNNING = true; $('#d-pause').textContent = '⏸'; runLoop();
}

function renderPathScript(cpId) {                             // 把某条路径重渲成剧本（fork 回放）
  const L = TreeLayout.layoutTree(TREE);
  const path = TreeLayout.pathToRoot(L.byId, cpId);
  const script = $('#d-script'); script.innerHTML = '';
  let prev = 50;
  for (const cp of path) {
    const st = cp.state || {};
    if (!st.who) continue;
    const t = document.createElement('div'); t.className = 'sp ' + st.who;
    let html = `<div class="sp-name">${esc(cp.user || st.who)}</div>`;
    if (st.tactic) html += `<div class="sp-paren">${esc(st.tactic)}</div>`;
    html += `<div class="sp-line">${esc(cp.final || '')}</div>`;
    t.innerHTML = html;
    if (cp.thought) { const os = document.createElement('div'); os.className = 'sp-os'; os.textContent = cp.thought; t.appendChild(os); }
    script.appendChild(t);
    spBeat((st.rel || 50) - prev); prev = st.rel || 50;
  }
  scrollScript();
}

window.addEventListener('load', () => {
  $('#d-start').addEventListener('click', start);
  $('#d-pause').addEventListener('click', togglePause);
  $('#d-reset').addEventListener('click', reset);
  $('#d-castbtn').addEventListener('click', openSetup);
  $('#d-open-setup').addEventListener('click', openSetup);
  $('#setup-close').addEventListener('click', closeSetup);
  $('#d-mapbtn').addEventListener('click', openMap);
  $('#map-close').addEventListener('click', closeMap);
  $('#d-injectbtn').addEventListener('click', inject);
  $('#d-inject').addEventListener('keydown', (e) => { if (e.key === 'Enter') inject(); });
  $('#d-forkgo').addEventListener('click', doFork);
  $('#d-forkcancel').addEventListener('click', cancelFork);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeMap(); closeSetup(); } });
});
