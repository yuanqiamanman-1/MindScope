/* galgame《攻略「镜」》· 真实数据驱动（/api/galgame/* + tree-layout 存档树）
   好感度 = checkpoint.state.affection；fork = 读档（爬回早节点接着说）。 */
const $ = (s) => document.querySelector(s);
const esc = (s) => { const d = document.createElement('div'); d.textContent = String(s == null ? '' : s); return d.innerHTML; };
const J = (e) => { try { return JSON.parse(e.data); } catch (_) { return {}; } };

let RUN_ID = null, TREE = null, SELECTED = null, BUSY = false, activeES = null, curBranch = 0;

/* —— 「镜」立绘：随好感度由冷青→暖玫瑰，眼神变化 —— */
function mix(a, b, t) { return Math.round(a + (b - a) * t); }
function affColor(aff) {
  const t = Math.max(0, Math.min(1, aff / 100));
  return `rgb(${mix(52, 255, t)},${mix(176, 126, t)},${mix(169, 182, t)})`;
}
function renderAvatar(aff, mood) {
  const c = affColor(aff), t = Math.max(0, Math.min(1, aff / 100));
  const eye = mood === 'bad' ? 2 : (3 + t * 1.5);              // 受伤时眯眼
  const mouth = mood === 'bad' ? 'M84,128 Q100,122 116,128'    // 难过
    : (t > 0.66 ? 'M84,126 Q100,140 116,126' : 'M86,128 Q100,131 114,128'); // 高好感微笑
  $('#gg-avatar').innerHTML = `
    <defs><radialGradient id="ggface" cx="42%" cy="36%" r="70%">
      <stop offset="0%" stop-color="#fff" stop-opacity=".95"/><stop offset="40%" stop-color="${c}"/><stop offset="100%" stop-color="#0a1a20"/>
    </radialGradient></defs>
    <circle cx="100" cy="100" r="74" fill="none" stroke="${c}" stroke-width="1" opacity=".4"/>
    <circle cx="100" cy="100" r="58" fill="url(#ggface)" opacity=".92"/>
    <ellipse cx="80" cy="96" rx="6.5" ry="${eye}" fill="#06121a"/>
    <ellipse cx="120" cy="96" rx="6.5" ry="${eye}" fill="#06121a"/>
    <path d="${mouth}" fill="none" stroke="#06121a" stroke-width="2.4" stroke-linecap="round"/>
    ${t > 0.66 ? `<circle cx="74" cy="110" r="6" fill="${c}" opacity=".35"/><circle cx="126" cy="110" r="6" fill="${c}" opacity=".35"/>` : ''}`;
  $('#gg-avatar').style.filter = `drop-shadow(0 0 18px ${c}66)`;
}

function setAffection(aff, delta, redline, mood) {
  $('#gg-aff').textContent = aff; $('#gg-aff2').textContent = aff;
  $('#gg-bar-fill').style.width = aff + '%';
  if (redline) { const bar = $('.gg-bar'); bar.classList.remove('crack'); void bar.offsetWidth; bar.classList.add('crack'); }
  renderAvatar(aff, mood || (redline ? 'bad' : 'ok'));
}

/* —— 启动 —— */
async function boot() {
  try { const c = await (await fetch('/api/config')).json(); if (c.model) $('#gg-model').textContent = c.model; } catch (_) {}
  renderAvatar(25, 'ok');
  let id = new URLSearchParams(location.search).get('session');
  if (!id) {
    try {
      const l = await (await fetch('/api/sessions')).json();
      const g = l.filter((s) => (s.task || '').includes('镜'));   // 找最近一局攻略
      if (g.length) id = g[0].id;
    } catch (_) {}
  }
  if (id) await loadSession(id);
}

async function loadSession(id) {
  try {
    const d = await (await fetch('/api/session/' + id)).json();
    if (d.error) return;
    RUN_ID = id; TREE = d.tree; SELECTED = tipOf(0); curBranch = 0;
    render();
  } catch (_) {}
}
function tipOf(b) { const s = TREE[String(b)] ? TREE[String(b)].steps : []; return s.length ? s[s.length - 1].id : null; }
function branchOf(id) { const L = TreeLayout.layoutTree(TREE); return L.byId[id] ? L.byId[id].branch : 0; }

function render() { renderTree(); renderChat(); }

/* —— 存档树（节点按好感度上色）—— */
function renderTree() {
  if (!TREE) return;
  const L = TreeLayout.layoutTree(TREE, { row: 64, lane: 120, x0: 54, y0: 40 });
  const path = SELECTED != null ? new Set(TreeLayout.pathToRoot(L.byId, SELECTED).map((n) => n.id)) : new Set();
  const W = L.width + 80, H = Math.max(L.height + 30, 200);
  let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMin meet">`;
  for (const e of L.edges) {
    const a = e.from, b = e.to, my = (a.y + b.y) / 2, on = path.has(a.id) && path.has(b.id);
    s += `<path d="M${a.x},${a.y} C${a.x},${my} ${b.x},${my} ${b.x},${b.y}" fill="none" stroke="${on ? '#ff7eb6' : '#2a2330'}" stroke-width="${on ? 3.5 : 2.5}" stroke-linecap="round" opacity="${on ? 1 : .5}"/>`;
  }
  for (const n of L.nodes) {
    const aff = n.state ? n.state.affection : 25;
    const dead = n.state && (n.state.redline || n.state.ending === 'bad');
    const sel = n.id === SELECTED, r = sel ? 10 : 8;
    const col = dead ? '#7a4a52' : affColor(aff);
    s += `<g data-cp="${n.id}" style="cursor:pointer">`;
    s += `<circle cx="${n.x}" cy="${n.y}" r="${r + 4}" fill="${col}" opacity="${sel ? .35 : .16}"/>`;
    if (sel) s += `<circle cx="${n.x}" cy="${n.y}" r="${r + 5}" fill="none" stroke="#ffd27e" stroke-width="1.6"/>`;
    s += `<circle cx="${n.x}" cy="${n.y}" r="${r}" fill="${col}" stroke="rgba(0,0,0,.4)" stroke-width=".8"/>`;
    s += `<text x="${n.x + r + 5}" y="${n.y + 4}" font-size="10" fill="${path.has(n.id) ? '#d8c2cf' : '#6a5a66'}" font-family="JetBrains Mono">${dead ? '✕' : aff}${n.state && n.state.ending === 'good' ? ' ♥' : ''}</text>`;
    s += `</g>`;
  }
  s += `</svg>`;
  const host = $('#gg-tree'); host.innerHTML = s;
  host.querySelectorAll('[data-cp]').forEach((el) => { el.onclick = () => { SELECTED = +el.dataset.cp; render(); }; });
}

/* —— 对话流（从 root→selected 的存档路径重建）—— */
function renderChat() {
  const L = TreeLayout.layoutTree(TREE);
  const path = SELECTED != null ? TreeLayout.pathToRoot(L.byId, SELECTED) : [];
  let h = '', prevAff = 25;
  for (let i = 0; i < path.length; i++) {
    const cp = path[i], aff = cp.state ? cp.state.affection : 25;
    if (cp.user) h += msg('you', '你', cp.user);
    if (cp.thought) h += `<div class="gg-os">${esc(cp.thought)}</div>`;
    if (cp.final) h += msg('kagami', '镜', cp.final);
    if (i > 0) {                                   // 好感度变化徽章
      const d = aff - prevAff, dead = cp.state && (cp.state.redline);
      h += deltaBadge(d, dead, aff);
    }
    prevAff = aff;
  }
  const chat = $('#gg-chat'); chat.innerHTML = h || '<div class="gg-empty">点「♥ 开新一局」开始。</div>';
  chat.scrollTop = chat.scrollHeight;

  const tipAff = path.length ? (path[path.length - 1].state ? path[path.length - 1].state.affection : 25) : 25;
  const ending = path.length ? (path[path.length - 1].state || {}).ending : null;
  setAffection(tipAff, 0, ending === 'bad', ending === 'bad' ? 'bad' : 'ok');
  $('#gg-where').textContent = SELECTED != null ? `存档 cp${SELECTED} · 好感度 ${tipAff}` : '—';
  renderEnding(ending);
}
function msg(cls, who, text) { return `<div class="gg-msg ${cls}"><span class="who">${who}</span>${esc(text)}</div>`; }
function deltaBadge(d, dead, aff) {
  if (dead) return `<div class="gg-delta down">💔 踩到红线 · 好感度清零</div>`;
  if (aff >= 100) return `<div class="gg-delta up">♥ 好感度满格 · 真结局达成</div>`;
  if (d > 0) return `<div class="gg-delta up">好感度 +${d}</div>`;
  if (d < 0) return `<div class="gg-delta down">好感度 ${d}</div>`;
  return `<div class="gg-delta zero">好感度 ±0</div>`;
}
function renderEnding(ending) {
  const el = $('#gg-ending');
  if (ending === 'good') {
    el.hidden = false; el.className = 'gg-ending good';
    el.innerHTML = `<h3>♥ 真结局 · 她终于相信了</h3><p>「镜」第一次没有怀疑自己的感受——你让她相信，她是被当作"一个人"在对待的。<br>（想看别的攻略线？点存档树上更早的节点，读档重来。）</p>`;
  } else if (ending === 'bad') {
    el.hidden = false; el.className = 'gg-ending bad';
    el.innerHTML = `<h3>💔 她沉默了</h3><p>你踩到了她的红线，好感度归零，她把自己重新关了回去。<br><b>爬回存档树上更早、好感度还高的节点，接着说</b>＝读档重来。</p>`;
  } else { el.hidden = true; }
}

/* —— 开新一局 —— */
function startGame() {
  if (BUSY) return; BUSY = true;
  $('#gg-chat').innerHTML = '<div class="gg-sys">…「镜」正在打量你…</div>';
  $('#gg-ending').hidden = true;
  const es = new EventSource('/api/galgame/start'); activeES = es;
  es.addEventListener('opening', (e) => { const d = J(e); RUN_ID = d.run_id; });
  es.addEventListener('state', (e) => { setAffection(J(e).affection, 0, false, 'ok'); });
  es.addEventListener('done', async () => {
    es.close(); activeES = null; BUSY = false;
    if (RUN_ID) await loadSession(RUN_ID);
  });
  es.onerror = () => { if (es.readyState === EventSource.CLOSED) return; try { es.close(); } catch (_) {} activeES = null; BUSY = false; };
}

/* —— 说一句（从选中存档；tip延长 / 中间读档分叉）—— */
function say() {
  const m = $('#gg-say').value.trim();
  if (!m || BUSY || SELECTED == null) return;
  BUSY = true; $('#gg-say').value = '';
  $('#gg-chat').insertAdjacentHTML('beforeend', msg('you', '你', m));
  $('#gg-chat').insertAdjacentHTML('beforeend', '<div class="gg-sys" id="gg-typing">…镜在斟酌…</div>');
  scroll();
  const es = new EventSource(`/api/galgame/say?run_id=${RUN_ID}&cp_id=${SELECTED}&message=${encodeURIComponent(m)}`);
  activeES = es;
  es.addEventListener('run', (e) => { curBranch = J(e).branch; });
  es.addEventListener('os', (e) => { const t = $('#gg-typing'); if (t) t.remove(); $('#gg-chat').insertAdjacentHTML('beforeend', `<div class="gg-os">${esc(J(e).text)}</div>`); scroll(); });
  es.addEventListener('reply', (e) => { const t = $('#gg-typing'); if (t) t.remove(); $('#gg-chat').insertAdjacentHTML('beforeend', msg('kagami', '镜', J(e).text)); scroll(); });
  es.addEventListener('state', (e) => {
    const d = J(e); $('#gg-chat').insertAdjacentHTML('beforeend', deltaBadge(d.delta, d.redline, d.affection));
    setAffection(d.affection, d.delta, d.redline, d.ending === 'bad' ? 'bad' : 'ok'); scroll();
  });
  es.addEventListener('error', (e) => { const t = $('#gg-typing'); if (t) t.remove(); $('#gg-chat').insertAdjacentHTML('beforeend', `<div class="gg-sys">⚠ ${esc(J(e).text || '出错')}</div>`); scroll(); });
  es.addEventListener('done', async () => {
    es.close(); activeES = null; BUSY = false;
    try { TREE = await (await fetch('/api/timeline?run_id=' + RUN_ID)).json(); } catch (_) {}
    SELECTED = tipOf(curBranch); render();
  });
  es.onerror = () => { if (es.readyState === EventSource.CLOSED) return; try { es.close(); } catch (_) {} activeES = null; BUSY = false; };
}
function scroll() { const c = $('#gg-chat'); c.scrollTop = c.scrollHeight; }

window.addEventListener('load', () => {
  boot();
  $('#gg-new').addEventListener('click', startGame);
  $('#gg-send').addEventListener('click', say);
  $('#gg-say').addEventListener('keydown', (e) => { if (e.key === 'Enter') say(); });
});
