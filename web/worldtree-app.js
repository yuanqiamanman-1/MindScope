/* 对话世界树 · 真实数据驱动（tree-layout + /api/session + /api/continue + /api/fork） */
const $ = (s) => document.querySelector(s);
const esc = (s) => { const d = document.createElement('div'); d.textContent = String(s == null ? '' : s); return d.innerHTML; };
const J = (e) => { try { return JSON.parse(e.data); } catch (_) { return {}; } };

let RUN_ID = null, TREE = null, SELECTED = null, BUSY = false, activeES = null, contBranch = 0, NEW_MODE = false;

async function boot() {
  try { const c = await (await fetch('/api/config')).json(); if (c.model) $('#wt-model').textContent = c.model; } catch (_) {}
  let id = new URLSearchParams(location.search).get('session');
  if (!id) {
    try {
      const l = await (await fetch('/api/sessions')).json();
      // 默认挑"最能展示世界树"的：分支多优先、其次步数多（空会话排除）
      const best = l.filter((s) => s.steps > 0)
        .sort((a, b) => (b.branches - a.branches) || (b.steps - a.steps))[0] || l[0];
      if (best) id = best.id;
    } catch (_) {}
  }
  if (!id) { newConversation(); return; }   // 没有会话 → 直接进入"开新对话"，别再甩去别的页
  await loadSession(id);
}

/* —— 开一棵新树：从世界树这里直接起新对话（不必回老调试器）—— */
function newConversation() {
  if (activeES) { try { activeES.close(); } catch (_) {} activeES = null; }
  RUN_ID = null; TREE = null; SELECTED = null; contBranch = 0; NEW_MODE = true; BUSY = false;
  $('#wt-sess').textContent = '新对话';
  $('#wt-tree').innerHTML = '<div class="ct-empty">🌱 在右下角描述一个任务，回车／发送，就种下这棵世界树的第一颗种子。<br>跑完后可在任意节点续聊、或改提示词时间旅行分叉。</div>';
  $('#wt-glass').innerHTML = '<div class="ct-empty">玻璃盒：发送后这里会实时显示 agent 的「思考→行动→观察」。</div>';
  $('#wt-at').innerHTML = '🌱 新对话 · 第一句话将开启一棵新世界树';
  const inp = $('#wt-input'); inp.placeholder = '描述一个新任务，开启一棵世界树…（例：查讯飞最近股价并写两句点评）';
  $('#wt-send').textContent = '种下';
  $('.ct-input').classList.add('newmode');
  inp.focus();
}

async function loadSession(id) {
  try {
    const d = await (await fetch('/api/session/' + id)).json();
    if (d.error) return fail(d.error);
    RUN_ID = id; TREE = d.tree; exitNewMode();
    $('#wt-sess').textContent = (d.task || id).slice(0, 20);
    SELECTED = lastCpOfBranch(0);
    render();
  } catch (e) { fail('加载会话失败'); }
}
function fail(m) { $('#wt-tree').innerHTML = `<div class="ct-empty">${esc(m)}</div>`; }

function lastCpOfBranch(b) { const s = TREE[String(b)] ? TREE[String(b)].steps : []; return s.length ? s[s.length - 1].id : null; }

/* —— 渲染世界树 SVG —— */
function render() { renderTree(); renderGlass(); }

function renderTree() {
  const L = TreeLayout.layoutTree(TREE);
  const path = SELECTED != null ? new Set(TreeLayout.pathToRoot(L.byId, SELECTED).map((n) => n.id)) : new Set();
  layoutOrganic(L);                          // 改写 n.x/n.y：父居中于子、从根往上长、撑满面板
  const W = L._W, H = L._H;
  let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMax meet">${defs()}`;
  s += ground(L);                            // 根部菌丝辉光 + 入土主干
  for (const e of L.edges) s += limb(e.from, e.to, path.has(e.from.id) && path.has(e.to.id), L._maxD);
  for (const n of L.nodes) s += node(n, path.has(n.id), n.id === SELECTED);
  s += `</svg>`;
  const host = $('#wt-tree'); host.innerHTML = s;
  host.querySelectorAll('[data-cp]').forEach((el) => { el.onclick = () => { SELECTED = +el.dataset.cp; render(); }; });
}

/* 把布局树（depth 已算好）摆成有机树：叶子顺序铺开、父居中于子、depth0 在底部、撑满面板。 */
function layoutOrganic(L) {
  const kids = {};
  L.nodes.forEach((n) => { if (n.parent != null && L.byId[n.parent]) (kids[n.parent] = kids[n.parent] || []).push(n.id); });
  for (const k in kids) kids[k].sort((a, b) => a - b);
  const GAP = 118, xpos = {}, seen = new Set();
  let cursor = 0;
  function assign(id) {
    if (seen.has(id)) return xpos[id]; seen.add(id);
    const cs = kids[id] || [];
    if (!cs.length) { xpos[id] = cursor; cursor += GAP; return xpos[id]; }
    const cx = cs.map(assign);
    xpos[id] = (Math.min.apply(null, cx) + Math.max.apply(null, cx)) / 2;
    return xpos[id];
  }
  L.nodes.filter((n) => n.parent == null || !L.byId[n.parent]).map((n) => n.id).sort((a, b) => a - b).forEach(assign);
  const maxD = Math.max(0, ...L.nodes.map((n) => n.depth));
  const xs = Object.values(xpos), minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs);
  const padX = 84, padTop = 52, padBot = 74;
  const ROW = maxD > 7 ? 72 : 118;                          // 深树收紧行距，免得细高失真
  const W = Math.max((maxX - minX || 1) + padX * 2, 480);   // 最小宽度：窄/线性树不被放大成巨球
  const H = Math.max(maxD * ROW + padTop + padBot, Math.round(W * 0.78));
  const innerH = H - padTop - padBot;
  L.nodes.forEach((n) => {
    n.x = (xpos[n.id] - minX) + padX;
    n.y = H - padBot - (maxD ? (n.depth / maxD) * innerH : 0);   // depth0=根=底部
  });
  L._W = W; L._H = H; L._maxD = maxD;
}

/* 根部：入土主干 + 菌丝辉光（每个根节点一处） */
function ground(L) {
  let g = '';
  L.nodes.filter((n) => n.depth === 0).forEach((n) => {
    g += `<ellipse cx="${n.x}" cy="${n.y + 34}" rx="52" ry="15" fill="#0c2a26" opacity=".5" filter="url(#wg)"/>`;
    g += `<ellipse cx="${n.x}" cy="${n.y + 34}" rx="30" ry="8" fill="#1c5c54" opacity=".5" filter="url(#wg)"/>`;
    g += `<path d="M${n.x},${n.y + 40} L${n.x},${n.y}" stroke="url(#wbk)" stroke-width="12" stroke-linecap="round" filter="url(#wg)"/>`;
    g += `<path d="M${n.x},${n.y + 36} C${n.x - 26},${n.y + 42} ${n.x - 34},${n.y + 50} ${n.x - 44},${n.y + 56}" stroke="#16463f" stroke-width="3" fill="none" stroke-linecap="round" opacity=".6"/>`;
    g += `<path d="M${n.x},${n.y + 36} C${n.x + 26},${n.y + 42} ${n.x + 34},${n.y + 50} ${n.x + 44},${n.y + 56}" stroke="#16463f" stroke-width="3" fill="none" stroke-linecap="round" opacity=".6"/>`;
  });
  return g;
}
function defs() {
  return `<defs>
    <filter id="wg" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <radialGradient id="wgc" cx="36%" cy="30%" r="72%"><stop offset="0%" stop-color="#d8fbf8"/><stop offset="42%" stop-color="#34b0a9"/><stop offset="100%" stop-color="#093230"/></radialGradient>
    <radialGradient id="wga" cx="36%" cy="30%" r="72%"><stop offset="0%" stop-color="#ffeec2"/><stop offset="42%" stop-color="#d6962a"/><stop offset="100%" stop-color="#3f2806"/></radialGradient>
    <radialGradient id="wgd" cx="36%" cy="30%" r="72%"><stop offset="0%" stop-color="#9fb0bd"/><stop offset="45%" stop-color="#4a586a"/><stop offset="100%" stop-color="#161d27"/></radialGradient>
    <linearGradient id="wbk" x1="0" y1="1" x2="0" y2="0"><stop offset="0%" stop-color="#3c6055"/><stop offset="100%" stop-color="#1d3b38"/></linearGradient>
  </defs>`;
}
/* 有机枝干：父(下,大y)→子(上,小y) 的曲线，靠根越粗，当前路径走流光 */
function limb(a, b, onPath, maxD) {
  const w = Math.max(2.4, 9.5 - b.depth * (6.5 / (maxD || 1)));
  const my = (a.y + b.y) / 2, dx = b.x - a.x;
  const d = `M${a.x},${a.y} C${a.x + dx * 0.1},${my} ${b.x - dx * 0.1},${my} ${b.x},${b.y}`;
  const col = onPath ? 'url(#wbk)' : '#1e2a2a';
  let p = `<path d="${d}" fill="none" stroke="${col}" stroke-width="${w}" stroke-linecap="round" opacity="${onPath ? 1 : .48}" filter="url(#wg)"/>`;
  if (onPath) p += `<path d="${d}" fill="none" stroke="#4fe6e0" stroke-width="2" stroke-linecap="round" stroke-dasharray="9 120" filter="url(#wg)"><animate attributeName="stroke-dashoffset" from="0" to="-258" dur="2.8s" repeatCount="indefinite"/></path>`;
  return p;
}
function node(n, onPath, sel) {
  const isFork = TREE && Object.values(TREE).some((b) => b.parent_cp === n.id);
  const grad = onPath ? 'wgc' : 'wgd', halo = onPath ? '#4fe6e0' : '#7a8896';
  const r = sel ? 11 : (isFork ? 10 : 8);
  let g = `<g data-cp="${n.id}" style="cursor:pointer">`;
  g += `<circle class="wtbreath" cx="${n.x}" cy="${n.y}" r="${r + 4}" fill="${halo}" opacity="${onPath ? .3 : .15}" filter="url(#wg)" style="animation-delay:${(n.id % 5) * 0.55}s"/>`;
  if (sel) g += `<circle cx="${n.x}" cy="${n.y}" r="${r + 5}" fill="none" stroke="#f2b24a" stroke-width="1.6" opacity=".85"/>`;
  g += `<circle cx="${n.x}" cy="${n.y}" r="${r}" fill="url(#${isFork && onPath ? 'wga' : grad})" stroke="rgba(0,0,0,.35)" stroke-width=".8" filter="url(#wg)"/>`;
  const lbl = n.final ? '✓' : ('cp' + n.id);
  g += `<text x="${n.x + r + 6}" y="${n.y + 4}" font-size="10.5" fill="${onPath ? '#9fb0c3' : '#5f7088'}" font-family="JetBrains Mono">${esc(lbl)}${n.action ? ' ' + esc(n.action.tool) : ''}</text>`;
  g += `</g>`;
  return g;
}

/* —— 玻璃盒：当前路径(root→selected)的真实推理 —— */
function renderGlass() {
  const L = TreeLayout.layoutTree(TREE);
  const path = SELECTED != null ? TreeLayout.pathToRoot(L.byId, SELECTED) : [];
  let h = '';
  for (const cp of path) {
    if (cp.user) h += `<div class="guser">${esc(cp.user)}</div>`;   // 这一轮的用户输入（人类发言，不只有输出）
    if (cp.rule) h += `<div class="grule">⏪ 时间旅行·这条分支追加了系统规则：<b>${esc(cp.rule)}</b></div>`;
    h += `<div class="gstep${cp.final ? ' final' : ''}">`;
    if (cp.thought) h += row('t', 'THOUGHT', cp.thought);
    if (cp.action) h += row('ac', 'ACTION', `${cp.action.tool}  ${JSON.stringify(cp.action.args || {})}`, true);
    if (cp.obs) h += row('ob', 'OBSERV', cp.obs, true);
    if (cp.final) h += row('f', '回复', cp.final);
    h += `</div>`;
  }
  if (!h) h = '<div class="ct-empty">空会话。</div>';
  $('#wt-glass').innerHTML = h;
  $('#wt-glass').scrollTop = $('#wt-glass').scrollHeight;
  // 时间旅行条 + 续聊提示
  const tip = SELECTED === lastCpOfBranch(branchOf(SELECTED));
  $('#wt-at').innerHTML = `📍 选中 <b>cp${SELECTED}</b> · ${tip ? '在末端续＝延长本枝' : '在中间续＝自动分叉新枝'}`;
}
function row(k, label, v, mono) {
  return `<div class="grow ${k}"><span class="k">${label}</span><span class="v${mono ? ' mono' : ''}">${esc(v)}</span></div>`;
}
function branchOf(id) { const L = TreeLayout.layoutTree(TREE); return L.byId[id] ? L.byId[id].branch : 0; }

function exitNewMode() {
  NEW_MODE = false;
  const inp = $('#wt-input'); inp.placeholder = '继续对话…（在选中节点接着说）';
  $('#wt-send').textContent = '发送';
  $('.ct-input').classList.remove('newmode');
}

/* —— 开新对话：第一句话 → /api/run 起一棵新树（SSE 实时进玻璃盒，跑完渲染世界树）—— */
function runNew(task) {
  if (!task || BUSY) return;
  BUSY = true; $('#wt-input').value = '';
  $('#wt-glass').innerHTML = '';
  appendGlass(`<div class="guser">${esc(task)}</div>`);
  appendGlass(`<div class="gturn">种树中…（agent 正在思考-行动）</div>`);
  $('#wt-tree').innerHTML = '<div class="ct-empty">🌱 世界树生长中…跑完即显示。</div>';
  $('#wt-sess').textContent = task.slice(0, 20);
  const es = new EventSource('/api/run?task=' + encodeURIComponent(task));
  activeES = es; let cur = null;
  const gs = () => { const d = document.createElement('div'); d.className = 'gstep'; $('#wt-glass').appendChild(d); cur = d; return d; };
  es.addEventListener('run', (e) => { RUN_ID = J(e).run_id; });
  es.addEventListener('thought', (e) => { gs(); cur.innerHTML += row('t', 'THOUGHT', J(e).text); scroll(); });
  es.addEventListener('action', (e) => { const a = J(e); if (!cur) gs(); cur.innerHTML += row('ac', 'ACTION', `${a.tool}  ${JSON.stringify(a.args || {})}`, true); scroll(); });
  es.addEventListener('observation', (e) => { if (!cur) gs(); cur.innerHTML += row('ob', 'OBSERV', J(e).text, true); scroll(); });
  es.addEventListener('final', (e) => { gs(); cur.classList.add('final'); cur.innerHTML += row('f', '回复', J(e).text); scroll(); });
  es.addEventListener('error', (e) => { if (!cur) gs(); cur.innerHTML += row('ob', 'ERROR', J(e).text || '出错', true); });
  es.addEventListener('done', async () => {
    es.close(); activeES = null; BUSY = false; exitNewMode();
    if (RUN_ID) await loadSession(RUN_ID);   // 用真实会话重渲染世界树 + 玻璃盒
  });
  es.onerror = () => { if (es.readyState === EventSource.CLOSED) return; try { es.close(); } catch (_) {} activeES = null; BUSY = false; };
}

/* —— 发送：新对话→起新树；否则→续聊 —— */
function sendMessage() {
  const msg = $('#wt-input').value.trim();
  if (!msg || BUSY) return;
  if (NEW_MODE || RUN_ID == null) runNew(msg);
  else sendContinue();
}

/* —— 续聊（SSE） —— */
function sendContinue() {
  const msg = $('#wt-input').value.trim();
  if (!msg || BUSY || SELECTED == null) return;
  BUSY = true; $('#wt-input').value = '';
  appendGlass(`<div class="guser">${esc(msg)}</div>`);
  appendGlass(`<div class="gturn">续聊中…（从 cp${SELECTED}）</div>`);
  const es = new EventSource(`/api/continue?run_id=${RUN_ID}&cp_id=${SELECTED}&message=${encodeURIComponent(msg)}`);
  activeES = es; let cur = null;
  const gs = () => { const d = document.createElement('div'); d.className = 'gstep'; $('#wt-glass').appendChild(d); cur = d; return d; };
  es.addEventListener('thought', (e) => { gs(); cur.innerHTML += row('t', 'THOUGHT', J(e).text); scroll(); });
  es.addEventListener('action', (e) => { const a = J(e); if (!cur) gs(); cur.innerHTML += row('ac', 'ACTION', `${a.tool}  ${JSON.stringify(a.args || {})}`, true); scroll(); });
  es.addEventListener('observation', (e) => { if (!cur) gs(); cur.innerHTML += row('ob', 'OBSERV', J(e).text, true); scroll(); });
  es.addEventListener('final', (e) => { gs(); cur.classList.add('final'); cur.innerHTML += row('f', '回复', J(e).text); scroll(); });
  es.addEventListener('continued', (e) => { contBranch = J(e).branch; });
  es.addEventListener('error', (e) => { if (!cur) gs(); cur.innerHTML += row('ob', 'ERROR', J(e).text || '出错', true); });
  es.addEventListener('done', async () => {
    es.close(); activeES = null; BUSY = false;
    try { TREE = await (await fetch('/api/timeline?run_id=' + RUN_ID)).json(); } catch (_) {}
    SELECTED = lastCpOfBranch(contBranch);
    render();
  });
  es.onerror = () => { if (es.readyState === EventSource.CLOSED) return; try { es.close(); } catch (_) {} activeES = null; BUSY = false; };
}
function appendGlass(html) { $('#wt-glass').insertAdjacentHTML('beforeend', html); scroll(); }
function scroll() { const g = $('#wt-glass'); g.scrollTop = g.scrollHeight; }

/* —— 时间旅行：改提示词从选中节点 fork —— */
function timeTravelFork() {
  const rule = $('#wt-rule').value.trim();
  if (BUSY || SELECTED == null) return;
  BUSY = true;
  if (rule) appendGlass(`<div class="grule">⏪ 从 cp${SELECTED} 追加规则重跑：<b>${esc(rule)}</b></div>`);
  appendGlass(`<div class="gturn">⏪ 改提示词重跑 → 分叉中…</div>`);
  const es = new EventSource(`/api/fork?run_id=${RUN_ID}&cp_id=${SELECTED}&append_system=${encodeURIComponent(rule)}`);
  activeES = es; let cur = null;
  const gs = () => { const d = document.createElement('div'); d.className = 'gstep'; $('#wt-glass').appendChild(d); cur = d; return d; };
  es.addEventListener('thought', (e) => { gs(); cur.innerHTML += row('t', 'THOUGHT', J(e).text); scroll(); });
  es.addEventListener('action', (e) => { const a = J(e); if (!cur) gs(); cur.innerHTML += row('ac', 'ACTION', `${a.tool}  ${JSON.stringify(a.args || {})}`, true); scroll(); });
  es.addEventListener('observation', (e) => { if (!cur) gs(); cur.innerHTML += row('ob', 'OBSERV', J(e).text, true); scroll(); });
  es.addEventListener('final', (e) => { gs(); cur.classList.add('final'); cur.innerHTML += row('f', '回复', J(e).text); scroll(); });
  es.addEventListener('forked', (e) => { contBranch = J(e).branch; });
  es.addEventListener('done', async () => {
    es.close(); activeES = null; BUSY = false; $('#wt-rule').value = '';
    try { TREE = await (await fetch('/api/timeline?run_id=' + RUN_ID)).json(); } catch (_) {}
    SELECTED = lastCpOfBranch(contBranch);
    render();
  });
  es.onerror = () => { if (es.readyState === EventSource.CLOSED) return; try { es.close(); } catch (_) {} activeES = null; BUSY = false; };
}

window.addEventListener('load', () => {
  boot();
  $('#wt-send').addEventListener('click', sendMessage);
  $('#wt-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') sendMessage(); });
  $('#wt-fork').addEventListener('click', timeTravelFork);
  $('#wt-new').addEventListener('click', newConversation);
});
