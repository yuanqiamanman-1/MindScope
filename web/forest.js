/* 森林 · 真实会话（/api/sessions）渲染成一片小世界树。
   每棵树按该会话真实的 步数/分支数 程序化生成（填满卡片、反映结构），不再用固定模板。 */
const esc = (s) => { const d = document.createElement('div'); d.textContent = String(s == null ? '' : s); return d.innerHTML; };
const HUES = ['h-cyan', 'h-green', 'h-cyan', 'h-amber', 'h-cyan', 'h-violet'];

function fruit(x, y, r, kind) {
  const g = kind === 'a' ? 'mga' : (kind === 'd' ? 'mgd' : 'mgc');
  const halo = kind === 'a' ? '#f2b24a' : '#4fe6e0';
  return `<g class="nd"><circle class="pl" cx="${x}" cy="${y}" r="${r + 2}" fill="${halo}"/>` +
    `<circle cx="${x}" cy="${y}" r="${r}" fill="url(#${g})" stroke="rgba(0,0,0,.35)" stroke-width=".6"/></g>`;
}
function limb(x1, y1, mx, my, x2, y2, w) {
  return `<path class="lf" d="M${x1},${y1} C${x1},${(y1 + y2) / 2} ${mx},${my} ${x2},${y2}" ` +
    `fill="none" stroke="url(#mbk)" stroke-width="${w}" stroke-linecap="round" filter="url(#mg)"/>`;
}

function miniTree(steps, branches) {
  steps = Math.max(1, steps);
  const nb = Math.max(1, Math.min(branches || 1, 5));
  const cx = 100, baseY = 142, forkY = nb > 1 ? 94 : 70;
  let s = '';
  // 主干
  s += limb(cx, baseY, cx, (baseY + forkY) / 2, cx, forkY, 8);
  // 枝条扇形展开
  const tips = [];
  if (nb === 1) {
    s += limb(cx, forkY, cx + 6, forkY - 30, cx + (steps > 4 ? 14 : 0), 26, 5);
    tips.push([cx + (steps > 4 ? 14 : 0), 26]);
    if (steps > 2) { s += fruit(cx + 3, (forkY + 26) / 2, 3.4); }
  } else {
    for (let i = 0; i < nb; i++) {
      const t = -1 + (2 * i) / (nb - 1);            // -1..1
      const tipX = 100 + t * 80, tipY = 24 + Math.abs(t) * 16;
      const midX = (cx + tipX) / 2 + t * 10, midY = (forkY + tipY) / 2;
      s += limb(cx, forkY, midX, midY, tipX, tipY, 5 - Math.abs(t) * 1.6);
      if (steps > nb + 1) s += fruit(midX, midY, 3.2);
      tips.push([tipX, tipY]);
    }
  }
  // 流光(主干→第一条枝)
  const fx = tips[Math.floor(tips.length / 2)];
  s += `<path class="sap" d="M${cx},${baseY} C${cx},${(baseY + forkY) / 2} ${cx},${forkY} ${cx},${forkY} L${fx[0]},${fx[1]}" fill="none"/>`;
  // 果实节点
  s += fruit(cx, baseY, 5.5);                        // 根
  s += fruit(cx, forkY, 6, nb > 1 ? 'a' : 'c');       // 分叉点(多枝=橙)
  for (const [tx, ty] of tips) s += fruit(tx, ty, 5);
  return s;
}

async function boot() {
  const host = document.querySelector('.forest');
  let list = [];
  try { list = await (await fetch('/api/sessions')).json(); } catch (_) {}
  list = list.filter((s) => (s.steps || 0) > 0);
  host.querySelectorAll('.seed').forEach((e) => e.remove());

  list.forEach((s, i) => {
    const when = (s.created || '').replace('T', ' ').slice(5, 16);
    const a = document.createElement('a');
    a.className = 'seed ' + HUES[i % HUES.length] + (i === 0 ? ' active' : '');
    a.href = 'convtree.html?session=' + s.id;
    a.innerHTML =
      (i === 0 ? '<span class="badge">最近</span>' : '') +
      `<svg viewBox="0 0 200 150">${miniTree(s.steps, s.branches)}</svg>` +
      `<div class="name">${esc((s.task || '(无任务)').slice(0, 18))}</div>` +
      `<div class="meta">${s.steps} 步 · ${s.branches} 枝 · ${esc(when)}</div>`;
    host.appendChild(a);
  });

  const n = document.createElement('a');
  n.className = 'seed new-seed'; n.href = 'index.html';
  n.textContent = '＋ 种一棵新树（开新会话）';
  host.appendChild(n);

  const cnt = document.querySelector('#f-count'); if (cnt) cnt.textContent = list.length;
  const br = document.querySelector('#f-branches');
  if (br) br.textContent = list.reduce((a, s) => a + (s.branches || 0), 0);
  if (!list.length) {
    const e = document.createElement('div');
    e.style.cssText = 'color:var(--ink-faint);font-size:12px;padding:24px';
    e.textContent = '森林还是空的——去「时间旅行调试器」种第一棵树吧。';
    host.insertBefore(e, host.firstChild);
  }
}
window.addEventListener('load', boot);
